from operator import itemgetter
import heapq
import logging
from typing import Optional, List, Any

from liaa.utils import hex_to_int, check_dht_value_type, digest_to_int, join_addr, split_addr, pack


log = logging.getLogger(__name__)  # pylint: disable=invalid-name


# pylint: disable=too-few-public-methods
class NodeType:
	Peer = "peer"
	Resource = "resource"


# pylint: disable=too-many-instance-attributes
class Node:
	# pylint: disable=bad-continuation
	def __init__(self, key: Optional[str] = None, node_type: int = NodeType.Peer,
		value: Optional[Any] = None):
		"""
		Node

		Simple object to encapsulate the concept of a Node (minimally an ID, but
		also possibly an IP and port if this represents a node on the network).
		This class should generally not be instantiated directly, as it is a low
		level construct mostly used by the router.

		A node can either be a peer, or a resource in the network

		Parameters
		----------
			digest_id: bytes
				A value between 0 and 2^160 (as byte array)
			key: str
				String identifier or this node
					is `IP:PORT` if node_type == NodeType.Peer
			node_type: int
				Indicator of whether the node represents a peer or a resource in
				the network
			value: Optional[Any]
				Payload associated with node (if self.node_type == NodeType.Resource)
		"""
		self.node_type = node_type
		self.value = value
		self.key = key
		# pylint: disable=invalid-name
		self.ip = None
		self.port = None

		if self.node_type == NodeType.Peer:
			self.ip, self.port = split_addr(self.key)

		self.digest = pack("I", self.key)
		self.hex = self.digest.hex()
		self.long_id = hex_to_int(self.digest.hex())

	def has_valid_value(self) -> bool:
		return check_dht_value_type(self.value)

	def is_same_node(self, other: "Node") -> bool:
		return self.key == other.key

	def distance_to(self, node: "Node") -> int:
		"""
		Get the distance between this node and another.

		Parameters
		----------
			node: Node
				Node against which to measure key distance
		"""
		return self.long_id ^ node.long_id

	def __eq__(self, other: "Node") -> bool:
		return self.key == other.key

	def __iter__(self):
		return iter([self.digest, self.ip, self.port])

	def __hash__(self):
		return self.long_id

	def __repr__(self):
		return repr([self.long_id, self.ip, self.port])

	def __str__(self):
		return self.node_type + "@" + self.key


class NodeHeap:
	def __init__(self, node, maxsize):
		"""
		NodeHead

		A heaped binary tree featuring a set of neighbors ordered by distance
		via `node.distance_to()`. The heap can contain up maxsize nodes, and
		will return min(len(NodeHeap), maxsize) nodes from __iter__

		Parameters
		----------
			node: Node
				The node to measure all distnaces from.
			maxsize: int
				The maximum size that this heap can grow to.
		"""
		self.node = node
		self.heap = []
		self.contacted = set()
		self.maxsize = maxsize

	def remove(self, peers: List["Node"]) -> None:
		"""
		Remove a list of peer ids from this heap. Note that while this
		heap retains a constant visible size (based on the iterator), it's
		actual size may be quite a bit larger than what's exposed.  Therefore,
		removal of nodes may not change the visible size as previously added
		nodes suddenly become visible.

		Parameters
		----------
			peers: List[Node]
				List of peers which to prune
		"""
		peers = set(peers)
		if not peers:
			return
		nheap = []
		for distance, node in self.heap:
			if node not in peers:
				heapq.heappush(nheap, (distance, node))
				continue
			log.debug("removing peer %s from node %s", str(node), str(node))
		self.heap = nheap

	def get_node(self, digest):
		for _, node in self.heap:
			if node.digest == digest:
				return node
		return None

	def have_contacted_all(self):
		return len(self.get_uncontacted()) == 0

	def get_ids(self):
		return [n.digest for n in self]

	def mark_contacted(self, node):
		self.contacted.add(node.digest)

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
			if node.digest == other.digest:
				return True
		return False

	def get_uncontacted(self):
		return [n for n in self if n.digest not in self.contacted]
