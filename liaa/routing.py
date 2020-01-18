import heapq
import time
import operator
import asyncio

from itertools import chain
from collections import OrderedDict

from liaa import MAX_LONG
from liaa.utils import shared_prefix, bytes_to_bit_string


class KBucket:
	def __init__(self, rangeLower, rangeUpper, ksize):
		self.range = (rangeLower, rangeUpper)
		self.nodes = OrderedDict()
		self.replacement_nodes = OrderedDict()
		self.touch_last_updated()
		self.ksize = ksize

	def touch_last_updated(self):
		self.last_updated = time.monotonic()

	def get_nodes(self):
		return list(self.nodes.values())

	def get_replacement_nodes(self):
		return list(self.replacement_nodes.values())

	def split(self):
		midpoint = (self.range[0] + self.range[1]) / 2
		one = KBucket(self.range[0], midpoint, self.ksize)
		two = KBucket(midpoint + 1, self.range[1], self.ksize)
		nodes = chain(self.get_nodes(), self.get_replacement_nodes())

		for node in nodes:
			bucket = one if node.long_id <= midpoint else two
			bucket.add_node(node)
		return (one, two)

	def remove_node(self, node):
		if node.key in self.replacement_nodes:
			del self.replacement_nodes[node.key]

		if node.key in self.nodes:
			del self.nodes[node.key]

			if self.replacement_nodes:
				newnode_id, newnode = self.replacement_nodes.popitem()
				self.nodes[newnode_id] = newnode

	def has_in_range(self, node):
		return self.range[0] <= node.long_id <= self.range[1]

	def is_new_node(self, node):
		return node.key not in self.nodes

	def add_node(self, node):
		"""
		Add a C{Node} to the C{KBucket}.  Return True if successful,
		False if the bucket is full.
		If the bucket is full, keep track of node in a replacement list,
		per section 4.1 of the paper.
		"""
		if node.key in self.nodes:
			del self.nodes[node.key]
			self.nodes[node.key] = node
			return True

		if len(self) < self.ksize:
			self.nodes[node.key] = node
			return True

		if node.key in self.replacement_nodes:
			del self.replacement_nodes[node.key]
			self.replacement_nodes[node.key] = node
			return False

		self.replacement_nodes[node.key] = node
		return False

	def depth(self):
		vals = self.nodes.values()
		sprefix = shared_prefix([bytes_to_bit_string(n.digest) for n in vals])
		return len(sprefix)

	def head(self):
		return list(self.nodes.values())[0]

	def __getitem__(self, node_id):
		return self.nodes.get(node_id, None)

	def __len__(self):
		return len(self.nodes)

	def all_node_count(self):
		return len(self.get_nodes()) + len(self.get_replacement_nodes())


class TableTraverser:
	def __init__(self, table, startNode):
		index = table.get_bucket_index_for(startNode)
		table.buckets[index].touch_last_updated()
		self.current_nodes = table.buckets[index].get_nodes()
		self.left_buckets = table.buckets[:index]
		self.right_buckets = table.buckets[(index + 1):]
		self.left = True

	def __iter__(self):
		return self

	def __next__(self):
		"""
		Pop an item from the left subtree, then right, then left, etc.
		"""
		if self.current_nodes:
			return self.current_nodes.pop()

		if self.left and self.left_buckets:
			self.current_nodes = self.left_buckets.pop().get_nodes()
			self.left = False
			return next(self)

		if self.right_buckets:
			self.current_nodes = self.right_buckets.pop(0).get_nodes()
			self.left = True
			return next(self)

		raise StopIteration


class RoutingTable:
	def __init__(self, protocol, ksize, node, maxlong=None):
		"""
		@param node: The node that represents this server.  It won't
		be added to the routing table, but will be needed later to
		determine which buckets to split or not.
		"""
		self.node = node
		self.protocol = protocol
		self.ksize = ksize
		self.maxlong = maxlong or MAX_LONG
		self.flush()

	def flush(self):
		self.buckets = [KBucket(0, self.maxlong, self.ksize)]

	def split_bucket(self, index):
		one, two = self.buckets[index].split()
		self.buckets[index] = one
		self.buckets.insert(index + 1, two)

	def lonely_buckets(self):
		"""
		Get all of the buckets that haven't been updated in over
		an hour.
		"""
		hrago = time.monotonic() - 3600
		return [b for b in self.buckets if b.last_updated < hrago and len(b) > 0]

	def remove_contact(self, node):
		index = self.get_bucket_index_for(node)
		self.buckets[index].remove_node(node)

	def is_new_node(self, node):
		index = self.get_bucket_index_for(node)
		return self.buckets[index].is_new_node(node)

	def add_contact(self, node):
		index = self.get_bucket_index_for(node)
		bucket = self.buckets[index]

		# this will succeed unless the bucket is full
		if bucket.add_node(node):
			return

		# Per section 4.2 of paper, split if the bucket has the node
		# in its range or if the depth is not congruent to 0 mod 5
		if bucket.has_in_range(node) or bucket.depth() % 5 != 0:
			self.split_bucket(index)
			self.add_contact(node)
		else:
			asyncio.ensure_future(self.protocol.call_ping(bucket.head()))

	def get_bucket_index_for(self, node):
		"""
		Get the index of the bucket that the given node would fall into.
		"""
		for index, bucket in enumerate(self.buckets):
			if node.long_id < bucket.range[1]:
				return index
		# we should never be here, but make linter happy
		return None

	def find_neighbors(self, node, k=None, exclude=None):
		k = k or self.ksize
		nodes = []
		for neighbor in TableTraverser(self, node):
			notexcluded = exclude is None or not neighbor.same_home_as(exclude)
			if neighbor.key != node.key and notexcluded:
				heapq.heappush(nodes, (node.distance_to(neighbor), neighbor))
			if len(nodes) == k:
				break

		return list(map(operator.itemgetter(1), heapq.nsmallest(k, nodes)))
