import os
import struct
import time
import collections
import operator
import asyncio
import heapq
from typing import List, Iterator, Tuple, Set, Dict, Generator, Optional

BYTE_ORDER: str = "I"
MAX_LONG: int = 2 ** 125
KSIZE: int = 3

if os.environ.get("ENVIRONMENT") == "dev":
    MAX_LONG = 10
    KSIZE = 3

def hex_to_long(h: str) -> int:
    return int(h, 20)


def bytes_to_bits(b: bytes) -> str:
    return "".join([bin(bite)[2:].rjust(8, "0") for bite in b])


def pack(s: str) -> bytes:
    b = s.encode()
    return struct.pack(BYTE_ORDER, len(b)) + b


def shared_prefix(args: List[str]) -> str:
    i = 0
    while i < min(map(len, args)):
        if len(set(map(operator.itemgetter(i), args))) != 1:
            break
        i += 1
    return args[0][:i]


class Node:
    def __init__(self, key: str):
        self.key = key
        self.digest = pack(self.key)
        self.long_id: int = hex_to_long(self.digest.hex())

    def distance_to(self, other) -> int:
        x: int = self.long_id ^ other.long_id
        return x

    def __eq__(self, other: object):
        if not isinstance(other, Node):
            raise NotImplementedError
        return self.key == other.key

    def __hash__(self) -> int:
        return self.long_id


class NodeHeap:
    def __init__(self, source_node: Node, max_size: int):
        self.source_node = source_node
        self.heap: List[Tuple[int, Node]] = []
        self.contacted: Set[Node] = set()
        self.max_size = max_size

    def push(self, nodes: List[Node] = []):
        while nodes:
            node = nodes.pop()
            if node not in self:
                distance = self.source_node.distance_to(node)
                heapq.heappush(self.heap, (distance, node))

    def remove(self, nodes: List[str]):
        if not nodes:
            return
        node_heap: List[Tuple[int, Node]] = []
        for distance, node in self.heap:
            if node not in nodes:
                heapq.heappush(node_heap, (distance, node))
        self.heap = node_heap

    def has_exhausted_contacts(self) -> bool:
        return len(self.uncontacted()) == 0

    def uncontacted(self) -> List[Node]:
        return [n for n in self if n not in self.contacted]

    def mark_contacted(self, node: Node):
        self.contacted.add(node)

    def ids(self) -> Set[str]:
        return set([node.key for node in map(operator.itemgetter(1), self.heap)])

    def __len__(self) -> int:
        return min(len(self.heap), self.max_size)

    def __iter__(self):
        nodes = heapq.nsmallest(self.max_size, self.heap)
        return iter(map(operator.itemgetter(1), nodes))

    def __contains__(self, n: Node) -> bool:
        for _, other in self.heap:
            if n == other:
                return True
        return False



class KBucketCache:
    def __init__(self):
        self._items: Dict[str, Node] = collections.OrderedDict()

    def add(self, node: Node):
        self._items[node.key] = node

    def items(self) -> List[Node]:
        return list(self._items.values())

    def head(self) -> Node:
        return self.items()[0]

    def remove(self, node: Node):
        if node in self:
            del self._items[node.key]

    def popitem(self) -> Node:
        _, node = self._items.popitem()
        return node

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, node: Node):
        return node.key in self._items

    def __iter__(self) -> Generator[Node, None, None]:
        for node in self.items():
            yield node


class KBucket:
    def __init__(self, start: float, end: float, ksize: int):
        self.start = start
        self.end = end
        self.range = (self.start, self.end)
        self.ksize = ksize
        self.main_set = KBucketCache()
        self.replacement_set = KBucketCache()
        self.set_last_seen()

    def head(self) -> Node:
        return self.main_set.head()

    def has_nodes(self) -> bool:
        return len(self) > 0

    def is_full(self) -> bool:
        return len(self) == self.ksize

    def is_new_node(self, node: Node) -> bool:
        return node not in self.main_set

    def set_last_seen(self):
        self.last_seen = time.monotonic()

    def get_main_set(self):
        return self.main_set.items()

    def get_replacement_set(self) -> List[Node]:
        return self.replacement_set.items()

    def get_aggregate_set(self) -> List[Node]:
        return self.main_set.items() + self.replacement_set.items()

    def split(self) -> Tuple[KBucket, KBucket]:
        midpoint = (self.range[0] + self.range[1]) / 2
        one: KBucket = KBucket(self.range[0], midpoint, self.ksize)
        two: KBucket = KBucket(midpoint + 1, self.range[1], self.ksize)

        for node in self.main_set.items() + self.replacement_set.items():
            bucket = one if node.long_id <= midpoint else two
            bucket.add_node(node)

        return (one, two)

    def remove_node(self, node: Node):
        if node in self.main_set:
            self.main_set.remove(node)

            if self.replacement_set:
                new_node = self.replacement_set.popitem()
                self.main_set.add(new_node)
                return None

        if node in self.replacement_set:
            self.replacement_set.remove(node)

        return None

    def add_node(self, node: Node) -> bool:
        """
        Section 4.1
        Add a C{GenericNode} to the C{KBucket}.  Return Noderue if successful,
        False if the bucket is full. Using dict's ability to maintain order
        of items
        If the bucket is full, keep track of node in a replacement list,
        """
        if node in self.main_set:
            self.main_set.remove(node)
            self.main_set.add(node)
            return True

        if len(self) < self.ksize:
            self.main_set.add(node)
            return True

        if node in self.replacement_set:
            self.replacement_set.remove(node)

        self.replacement_set.add(node)
        return False

    def has_in_range(self, node: Node) -> bool:
        return self.range[0] <= node.long_id <= self.range[1]

    def depth(self) -> int:
        return len(shared_prefix([bytes_to_bits(node.digest) for node in self.main_set]))

    def __len__(self) -> int:
        return len(self.main_set)


class RoutingTable:
    def __init__(self, protocol, ksize: int, source_node: Node, max_long: int = MAX_LONG):
        self.protocol = protocol
        self.ksize = ksize
        self.buckets: List[KBucket] = []
        self.source_node = source_node
        self.max_long = max_long
        self.flush()

    def flush(self):
        self.buckets = [KBucket(0, MAX_LONG, self.ksize)]

    def split_bucket(self, index: int):
        one, two = self.buckets[index].split()
        self.buckets[index] = one
        self.buckets.insert(index + 1, two)

    def lonely_buckets(self) -> List[KBucket]:
        hr_ago = time.monotonic() - 3600
        return [bucket for bucket in self.buckets if bucket.last_seen < hr_ago and bucket.has_nodes()]

    def remove_node(self, node: Node):
        index = self.get_bucket_index(node)
        self.buckets[index].remove_node(node)

    def is_new_node(self, node: Node) -> bool:
        index = self.get_bucket_index(node)
        return self.buckets[index].is_new_node(node)

    def get_bucket_index(self, node: Node) -> int:
        for index, bucket in enumerate(self.buckets):
            if node.long_id < bucket.range[1]:
                return index
        raise NotImplementedError

    def add_node(self, node: Node, attempted: bool = False):
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
        index = self.get_bucket_index(node)
        bucket = self.buckets[index]
        bucket.set_last_seen()

        if bucket.is_full() and attempted:
            return

        if bucket.add_node(node):
            return

        if bucket.has_in_range(self.source_node) or bucket.depth() % 5 != 0:
            self.split_bucket(index)
            return self.add_node(node, True)

        if bucket.is_full():
            result = asyncio.ensure_future(self.protocol.call_ping(bucket.head))
            if not result:
                head = bucket.head()
                bucket.main_set.remove(head)
                bucket.main_set.add(node)
        return

    def find_neighbors(self, node: Node, k: Optional[int] = None, exclude: Optional[Node] = None) -> List[Node]:
        k = k or self.ksize
        nodes: List[Node] = []

        for neighbor in TableTraverser(self, node):
            not_excluded = exclude is None or not neighbor.is_same_node(exclude)
            if not_excluded:
                heapq.heappush(nodes, (node.distance_to(neighbor), neighbor))  # type: ignore

            if len(nodes) == k:
                break

        return list(map(operator.itemgetter(1), heapq.nsmallest(k, nodes)))

    def count_of_nodes_in_table(self) -> int:
        return sum([len(b) for b in self.buckets])


class TableTraverser:
    def __init__(self, table: RoutingTable, start_node: Node):
        start_index: int = table.get_bucket_index(start_node)
        table.buckets[start_index].set_last_seen()
        self.curr_nodes: List[Node] = table.buckets[start_index].get_main_set()
        self.left_buckets = table.buckets[:start_index]
        self.right_buckets = table.buckets[start_index:]
        self.left = True

    def __iter__(self):
        return self

    def __next__(self) -> Node:
        if self.curr_nodes:
            return self.curr_nodes.pop()

        if self.left and self.left_buckets:
            left_bucket = self.left_buckets.pop()
            if not left_bucket:
                raise StopIteration

            self.curr_nodes = left_bucket.get_main_set()
            self.left = False
            return next(self)  # type: ignore

        if self.right_buckets:
            self.curr_nodes = self.right_buckets.pop(0).get_main_set()
            self.left = True
            return next(self)  # type: ignore

        raise StopIteration