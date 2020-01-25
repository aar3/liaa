from operator import itemgetter
import heapq
import logging

from liaa import MAX_LONG
from liaa.utils import hex_to_int, check_dht_value_type, split_addr, pack


log = logging.getLogger(__name__)  # pylint: disable=invalid-name


# pylint: disable=too-many-instance-attributes
class Node:
	def __init__(self, key, value=None):
		"""
		Simple object to encapsulate the concept of a Node (minimally an ID, but
		also possibly an IP and port if this represents a node on the network).
		This class should generally not be instantiated directly, as it is a low
		level construct mostly used by the router.

		A node can either be a peer, or a resource in the network
		"""
		self.value = value
		self.key = key
		self.node_type = 'ambiguous'
		# pylint: disable=invalid-name
		self.ip = None
		self.port = None

		try:
			self.ip, self.port = split_addr(self.key)
		except ValueError:
			pass

		self.digest = pack(self.key)
		self.hex = self.digest.hex()
		self.long_id = hex_to_int(self.digest.hex())
		if self.long_id > MAX_LONG + 1:
			raise OverflowError('node.long_id cannot exceed ' + str(MAX_LONG))

	def has_valid_value(self):
		return check_dht_value_type(self.value)

	def is_same_node(self, other):
		return self.key == other.key

	def distance_to(self, node):
		"""
		Section 2.1

		We calculate the XOR, the bitwise exclusive or, interpreted
		as an integer - in order to get the distance between this node and another.
		"""
		return self.long_id ^ node.long_id

	def is_peer_node(self):
		return isinstance(self.ip, str) and isinstance(self.port, int)

	def __eq__(self, other):
		return self.key == other.key

	def __iter__(self):
		return iter([self.key, self.ip, self.port])

	def __hash__(self):
		return self.long_id

	def __str__(self):
		return self.node_type + "@" + self.key


class PeerNode(Node):
	def __init__(self, key):
		"""
		Referenced as the {node} in the protocol
		"""
		super(PeerNode, self).__init__(key)
		self.node_type = "peer"


class ResourceNode(Node):
	def __init__(self, key, value, birthday=None):
		"""
		Referenced as the {key, value} pair in the protocol
		"""
		super(ResourceNode, self).__init__(key, value)
		self.node_type = "resource"
		self.birthday = birthday


class NodeHeap:
	def __init__(self, node, maxsize):
		"""
		A heaped binary tree featuring a set of neighbors ordered by distance
		via `node.distance_to()`. The heap can contain up maxsize nodes, and
		will return min(len(NodeHeap), maxsize) nodes from __iter__
		"""
		self.node = node
		self.heap = []
		self.contacted = set()
		self.maxsize = maxsize

	def remove(self, nodes):
		"""
		Remove a list of peer ids from this heap. Note that while this
		heap retains a constant visible size (based on the iterator), it's
		actual size may be quite a bit larger than what's exposed.  Therefore,
		removal of nodes may not change the visible size as previously added
		nodes suddenly become visible.
		"""
		nodes = set(nodes)
		if not nodes:
			return
		nheap = []
		for distance, node in self.heap:
			if node not in nodes:
				heapq.heappush(nheap, (distance, node))
				continue
			log.debug("removing peer %s from node %s", str(node), str(node))
		self.heap = nheap

	def get_node(self, key):
		for _, node in self.heap:
			if node.key == key:
				return node
		return None

	def have_contacted_all(self):
		return len(self.get_uncontacted()) == 0

	def get_ids(self):
		return [n.key for n in self]

	def mark_contacted(self, node):
		self.contacted.add(node.key)

	def popleft(self):
		return heapq.heappop(self.heap)[1] if self else None

	def push(self, nodes):
		"""
		Push nodes onto heap.
		"""
		if not isinstance(nodes, list):
			nodes = [nodes]

		for node in nodes:
			if node not in self:
				distance = self.node.distance_to(node)
				heapq.heappush(self.heap, (distance, node))

	def __len__(self):
		return min(len(self.heap), self.maxsize)

	def __iter__(self):
		nodes = heapq.nsmallest(self.maxsize, self.heap)
		return iter(map(itemgetter(1), nodes))

	def __contains__(self, node):
		for _, other in self.heap:
			if node.key == other.key:
				return True
		return False

	def get_uncontacted(self):
		return [n for n in self if n.key not in self.contacted]
