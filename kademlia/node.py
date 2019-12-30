from operator import itemgetter
import heapq
import logging
from typing import Optional, List, Any

from kademlia.utils import hex_to_int, check_dht_value_type, digest_to_int


log = logging.getLogger(__name__)  # pylint: disable=invalid-name


# pylint: disable=too-few-public-methods
class NodeType:
	Peer = "peer"
	Resource = "resource"


# pylint: disable=too-many-instance-attributes
class Node:
	# pylint: disable=bad-continuation
	def __init__(self,
		digest_id: bytes,
		ip: Optional[str] = None,
		port: Optional[int] = None,
		type: int = NodeType.Peer,  # pylint: disable=redefined-builtin
		value: Optional[Any] = None
	):
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
			ip: str
				Optional IP address where this Node lives
			port:
				Optional port for this Node (set when IP is set)
			type: int
				Indicator of whether the node represents a peer or a resource in
				the network
			value: Optional[Any]
				Payload associated with node (if self.type == NodeType.Resource)
		"""

		# byte array composed of int_to_digest(self.int_id)
		self.digest_id = digest_id
		self.int_id = digest_to_int(self.digest_id)
		self.hex = self.digest_id.hex()
		self.long_id = hex_to_int(self.digest_id.hex())

		self.ip = ip  # pylint: disable=invalid-name
		self.port = port

		self.type = type
		self.value = value

	def has_valid_value(self) -> bool:
		return check_dht_value_type(self.value)

	def is_same_node(self, node: "Node") -> bool:
		return self.ip == node.ip and self.port == node.port

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
		# if we're dealing with a peer node then we determine sameness
		# by the two nodes having the same server
		if self.type == NodeType.Peer:
			return self.ip == other.ip and self.port == other.port

		# if we're dealing with a resource node, we say two nodes are the same
		# if they have the same value
		return self.value == other.value

	def __iter__(self):
		return iter([self.digest_id, self.ip, self.port])

	def __hash__(self):
		return self.long_id

	def __repr__(self):
		return repr([self.long_id, self.ip, self.port])

	def __str__(self):
		# return f"<{self.type}, {self.ip}, {self.port}, {self.long_id}>"
		if self.type == NodeType.Peer:
			return f"{self.type}@{self.ip}:{self.port}"
		return f"{self.type}@{self.long_id}"


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
			if node.digest_id not in peers:
				heapq.heappush(nheap, (distance, node))
				continue
			log.debug("removing peer %s from node %s", str(node), str(node))
		self.heap = nheap

	def get_node(self, node_id):
		for _, node in self.heap:
			if node.digest_id == node_id:
				return node
		return None

	def have_contacted_all(self):
		return len(self.get_uncontacted()) == 0

	def get_ids(self):
		return [n.digest_id for n in self]

	def mark_contacted(self, node):
		self.contacted.add(node.digest_id)

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
			if node.digest_id == other.digest_id:
				return True
		return False

	def get_uncontacted(self):
		return [n for n in self if n.digest_id not in self.contacted]
