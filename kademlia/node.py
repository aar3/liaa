from operator import itemgetter
import heapq
# pylint: disable=unused-wildcard-import,wildcard-import
from typing import *

from kademlia.utils import hex_to_base_int, digest


class Node:

	def __init__(self, 
		node_id: int,
		 ip: Optional[str] = None, 
		 port: Optional[int] = None
	):
		"""
		Node
		
		Simple object to encapsulate the concept of a Node (minimally an ID, but
		also possibly an IP and port if this represents a node on the network).
		This class should generally not be instantiated directly, as it is a low
		level construct mostly used by the router.

		Parameters
		----------
			node_id: int
				A value between 0 and 2^160
			ip: str
				Optional IP address where this Node lives
			port:
				Optional port for this Node (set when IP is set)
		"""
		self.id = node_id  # pylint: disable=invalid-name
		self.ip = ip  # pylint: disable=invalid-name
		self.port = port
		self.long_id = hex_to_base_int(node_id.hex())

	def is_same_node(self, node):
		return self.ip == node.ip and self.port == node.port

	def distance_to(self, node):
		"""
		Get the distance between this node and another.
		"""
		return self.long_id ^ node.long_id

	def __eq__(self, other):
		return self.ip == other.ip and self.port == other.port

	def __iter__(self):
		"""
		Enables use of Node as a tuple - i.e., tuple(node) works.
		"""
		return iter([self.id, self.ip, self.port])

	def __hash__(self):
		return self.long_id

	def __repr__(self):
		return repr([self.long_id, self.ip, self.port])

	def __str__(self):
		return "%s:%s" % (self.ip, str(self.port))


class Resource:
	def __init__(self, key: Union[str, bytes]):
		"""
		Resource

		Is a small wrapper abstraction used to represent a non-node
		resource in the network (i.e., a value)
		"""
		self.key = key
		self.long_id = hex_to_base_int(digest(self.key))


TNode = NewType("TNode", Node)

class NodeHeap:
	"""
	A heap of nodes ordered by distance to a given node.
	"""
	def __init__(self, node, maxsize):
		"""
		Constructor.

		@param node: The node to measure all distnaces from.
		@param maxsize: The maximum size that this heap can grow to.
		"""
		self.node = node
		self.heap = []
		self.contacted = set()
		self.maxsize = maxsize

	def remove(self, peers):
		"""
		Remove a list of peer ids from this heap.  Note that while this
		heap retains a constant visible size (based on the iterator), it's
		actual size may be quite a bit larger than what's exposed.  Therefore,
		removal of nodes may not change the visible size as previously added
		nodes suddenly become visible.
		"""
		peers = set(peers)
		if not peers:
			return
		nheap = []
		for distance, node in self.heap:
			if node.id not in peers:
				heapq.heappush(nheap, (distance, node))
		self.heap = nheap

	def get_node(self, node_id):
		for _, node in self.heap:
			if node.id == node_id:
				return node
		return None

	def have_contacted_all(self):
		return len(self.get_uncontacted()) == 0

	def get_ids(self):
		return [n.id for n in self]

	def mark_contacted(self, node):
		self.contacted.add(node.id)

	def popleft(self):
		return heapq.heappop(self.heap)[1] if self else None

	def push(self, nodes):
		"""
		Push nodes onto heap.

		@param nodes: This can be a single item or a C{list}.
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
			if node.id == other.id:
				return True
		return False

	def get_uncontacted(self):
		return [n for n in self if n.id not in self.contacted]
