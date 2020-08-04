import operator
import heapq
import time
import logging

from _typing import *

from liaa import MAX_LONG
from liaa.utils import hex_to_int, check_dht_value_type, split_addr, pack


log = logging.getLogger(__name__)


class Node:
    def __init__(self, key: str):
        """
		Simple object to encapsulate the concept of a Node (minimally an ID, but
		also possibly an IP and port if this represents a node on the network).
		This class should generally not be instantiated directly, as it is a low
		level construct mostly used by the router.
		"""
        self.key = key
        # self.value: Optional[bytes] = value
        self.digest: bytes = pack(self.key)
        self.hex: str = self.digest.hex()
        self.long_id: int = hex_to_int(self.digest.hex())

        if self.long_id > MAX_LONG + 1:
            raise OverflowError("node long_id cannot exceed %i" % MAX_LONG)

    def is_same_node(self, other: "Node") -> bool:
        return self.key == other.key

    def distance_to(self, node: "Node") -> int:
        """
		Section 2.1

		We calculate the XOR, the bitwise exclusive or, interpreted
		as an integer - in order to get the distance between this node and another.
		"""
        return self.long_id ^ node.long_id

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Node):
            raise NotImplementedError
        return self.long_id == other.long_id

    def __hash__(self) -> int:
        return self.long_id

    def __str__(self) -> str:
        return self.__class__.__name__ + "@" + self.key

    def __iter__(self) -> Iterator[object]:
        raise NotImplementedError


class PingNode(Node):
    """
    Referenced as the {node} in the protocol
    """

    def addr(self) -> IPv4:
        return split_addr(self.key)

    def ping(self) -> None:
        # TODO: implment some caller dialing (ip, port)
        _ip, _port = self.addr()

    def __iter__(self) -> Iterator[object]:
        # TODO: the only difference between a PingNode and IndexNode
        # is that a PingNode can call ping("IP(a):Port(a)")
        ip, port = split_addr(self.key)
        return iter((self.key, ip, port))


class IndexNode(Node):
    def __init__(
        self, key: str, value: Optional[bytes], birthday: float = Optional[float]
    ):
        """
		Referenced as the {key, value} pair in the protocol
		"""
        super(IndexNode, self).__init__(key)
        self.value = value
        self.birthday = birthday or time.monotonic()

    def has_valid_value(self) -> bool:
        return check_dht_value_type(self.value)

    def as_dict(self) -> Dict[str, Optional[bytes]]:
        return {self.key: self.value}

    def __iter__(self) -> Iterator[object]:
        return iter((self.key, self.value, self.birthday))

# TODO: what is this? <(‘-‘<) 
GenericNode = Union[PingNode, IndexNode]
HeapNode = Tuple[float, GenericNode]


class NodeHeap:
    def __init__(self, node: GenericNode, maxsize: int):
        """
		A heap of nodes using distance as the sorting metric
		"""

        # TODO: NodeHeap needs an index for O(1) lookup of nodes
        self.node = node
        self.heap: List[HeapNode] = []
        self.contacted: Set[str] = set()
        self.maxsize = maxsize

    def remove(self, nodes: List[str]) -> None:
        """
		Remove a list of peer ids from this heap. Note that while this
		heap retains a constant visible size (based on the iterator), it's
		actual size may be quite a bit larger than what's exposed.  Therefore,
		removal of nodes may not change the visible size as previously added
		nodes suddenly become visible.
		"""
        nodes_as_set = set(nodes)
        if not nodes_as_set:
            return

        nheap: List[HeapNode] = []
        for distance, node in self.heap:
            if node.key not in nodes_as_set:
                heapq.heappush(nheap, (distance, node))
            else:
                log.debug("removing peer %s from node %s", str(node), str(node))
        self.heap = nheap

    def get_node(self, key: str) -> Optional[GenericNode]:
        for _, node in self.heap:
            if node.key == key:
                return node
        return None

    def has_exhausted_contacts(self) -> bool:
        return len(self.get_uncontacted()) == 0

    def get_ids(self) -> List[str]:
        return [n.key for n in map(operator.itemgetter(1), self.heap)]

    def get_all_ids(self) -> List[str]:
        return [n.key for n in map(operator.itemgetter(1), self.heap)]

    def get_uncontacted(self) -> List[GenericNode]:
        return [n for n in self if n.key not in self.contacted]

    def get_concatcted(self) -> List[GenericNode]:
        return [n for n in self if n.key in self.contacted]

    def mark_contacted(self, node: GenericNode) -> None:
        self.contacted.add(node.key)

    def popleft(self) -> Optional[GenericNode]:
        return heapq.heappop(self.heap)[1] if self else None

    def push(self, nodes: List[GenericNode]) -> None:
        """
		Push nodes onto heap.
		"""
        if not isinstance(nodes, list):
            raise ValueError("push expects type list, found ", type(nodes))
        for node in nodes:
            if node not in self:
                distance = self.node.distance_to(node)
                heapq.heappush(self.heap, (distance, node))

    def true_size(self) -> int:
        return len(self.heap)

    def __len__(self) -> int:
        return min(len(self.heap), self.maxsize)

    def __iter__(self) -> Iterator[GenericNode]:
        nodes = heapq.nsmallest(self.maxsize, self.heap)
        return iter(map(operator.itemgetter(1), nodes))

    def __contains__(self, node: GenericNode) -> bool:
        # TODO: need that index here for constant lookup
        for _, other in self.heap:
            if node.key == other.key:
                return True
        return False
