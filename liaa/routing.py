import heapq
import time
import operator
import asyncio

from itertools import chain
from collections import OrderedDict

from liaa import MAX_LONG
from liaa.utils import shared_prefix, bytes_to_bit_string


class ListNode:
	# pylint: disable=redefined-builtin,too-few-public-methods
	def __init__(self, val, prev=None, next=None):
		self.val = val
		self.prev = prev
		self.next = next

	def __str__(self):
		return str((self.prev, self.val, self.next))


class DoubleLinkedList:
	def __init__(self):
		self.head = None
		self.tail = None
		self._len = 0

	def add(self, node):
		if not self.head:
			self.head = node
		else:
			node.prev = self.tail
			self.tail.next = node
		self.tail = node
		self._len += 1

	def remove(self, node):
		if node == self.tail == self.head:
			self.tail = self.head = None

		elif not node.prev:
			self.head = node.next
			self.head.prev = None

		elif not node.next:
			self.tail = node.prev
			self.tail.next = None

		else:
			node.next.prev = node.prev
			node.prev = node.next

		self._len -= 1

	def __len__(self):
		return self._len

	def items(self):
		items = []
		curr = self.head
		while curr:
			items.append(str(curr))
			curr = curr.next
		return items


class LRSCache:
	def __init__(self, maxsize):
		"""
		Manual implementation of a least recently seen cache where the tail
		of the DoubleLinkedList is the latest seen node

		(Not currently used, using basic Python dict)
		"""
		self.list = DoubleLinkedList()
		self.maxsize = maxsize
		self.cache = {}

	def add(self, val):
		if val in self.cache:
			self.remove(val)
		node = ListNode(val)
		self.cache[val] = node
		self.list.add(node)

	def remove(self, val):
		if not val in self.cache:
			return False
		node = self.cache[val]
		del self.cache[val]
		self.list.remove(node)
		return None

	def __len__(self):
		return len(self.cache)


class KBucket:
	def __init__(self, lower_bound, upper_bound, ksize):
		self.range = (lower_bound, upper_bound)
		self.nodes = OrderedDict()
		self.replacement_nodes = OrderedDict()
		self.set_last_seen()
		self.ksize = ksize

	def set_last_seen(self):
		self.last_seen = time.monotonic()

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

	def add_node(self, node):
		"""
		Section 4.1

		Add a C{Node} to the C{KBucket}.  Return True if successful,
		False if the bucket is full. Using dict's ability to maintain order
		of items

		If the bucket is full, keep track of node in a replacement list,
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

	def depth(self):
		vals = self.nodes.values()
		sprefix = shared_prefix([bytes_to_bit_string(n.digest) for n in vals])
		return len(sprefix)

	def is_full(self):
		return len(self) == self.ksize

	def head(self):
		return list(self.nodes.values())[0]

	def has_in_range(self, node):
		return self.range[0] <= node.long_id <= self.range[1]

	def is_new_node(self, node):
		return node.key not in self.nodes

	def total_nodes(self):
		return len(self.get_nodes()) + len(self.get_replacement_nodes())

	def __getitem__(self, node_id):
		return self.nodes.get(node_id, None)

	def __len__(self):
		return len(self.nodes)


class TableTraverser:
	def __init__(self, table, startNode):
		index = table.get_bucket_index_for(startNode)
		table.buckets[index].set_last_seen()
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
		Section 2.4

		The routing table is a binary tree whose leaves are k-buckets, with
		each k-bucket being a leaf of the tree, containing nodes with a common
		prefix ID
		"""
		self.node = node
		self.protocol = protocol
		self.cache = LRSCache(maxsize=20)
		self.ksize = ksize
		self.maxlong = maxlong or MAX_LONG
		self.flush()

	def flush(self):
		""" Each routing table starts with a single k-bucket """
		self.buckets = [KBucket(0, self.maxlong, self.ksize)]

	def split_bucket(self, index):
		one, two = self.buckets[index].split()
		self.buckets[index] = one
		self.buckets.insert(index + 1, two)

	def lonely_buckets(self):
		"""
		Get all of the buckets that haven't been updated in over an hour.
		"""
		hrago = time.monotonic() - 3600
		return [b for b in self.buckets if b.last_seen < hrago and len(b) > 0]

	def remove_contact(self, node):
		""" Remove a node from its associated k-bucket """
		index = self.get_bucket_index_for(node)
		self.buckets[index].remove_node(node)

	def is_new_node(self, node):
		""" Determine if the node's intended k-bucket already has the node """
		index = self.get_bucket_index_for(node)
		return self.buckets[index].is_new_node(node)

	def add_contact(self, node, attempted=False):
		"""
		Add a node to the routing table

		Section 2.2

		If a k-bucket is full, call the head (last-seen node), if a response
		is received, discard the new node, else replace the new node with the
		non-responsive head. This implementation also acts as a form of DOS
		resistance

		Section 2.4

		If the intended k-bucket for `node` has len() < ksize, simply add
		the node to the k-bucket. If the intended-kbucket has len() == ksize,
		and the intended k-bucket's range includes `self.node` then the k-bucket
		is split into two new buckets, with the original buckets nodes being
		distributed into each bucket accordingly. If this derived k-bucket
		is full after splitting, and the `node` is intended to go into this
		k-bucket, then the node is dropped

		Section 4.2

		For accelerated lookups, we also split the k-bucket if its depth % b is
		not congruent to 0
		"""
		index = self.get_bucket_index_for(node)
		bucket = self.buckets[index]
		bucket.set_last_seen()

		if bucket.is_full() and attempted:
			return None

		if bucket.add_node(node):
			return None

		if bucket.has_in_range(self.node) or bucket.depth() % 5 != 0:
			self.split_bucket(index)
			return self.add_contact(node, True)

		if bucket.is_full():
			result = asyncio.ensure_future(self.protocol.call_ping(bucket.head()))
			if not result:
				items = bucket.nodes.items()
				items[0] = (node.key, node)
				bucket.nodes = dict(zip(items))
		return None


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
			notexcluded = exclude is None or not neighbor.is_same_node(exclude)
			if neighbor.key != node.key and notexcluded:
				heapq.heappush(nodes, (node.distance_to(neighbor), neighbor))
			if len(nodes) == k:
				break

		return list(map(operator.itemgetter(1), heapq.nsmallest(k, nodes)))

	def num_buckets(self):
		return len(self.buckets)

	def num_nodes(self):
		return sum([len(b) for b in self.buckets])

	def total_nodes(self):
		return sum([b.total_nodes() for b in self.buckets])
