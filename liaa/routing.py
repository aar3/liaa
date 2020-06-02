import heapq
import time
import logging
import operator
import asyncio
import collections
from _typing import *

from itertools import chain

from liaa import MAX_LONG
from liaa.utils import shared_prefix, bytes_to_bits
from liaa.node import GenericNode


log = logging.getLogger(__name__)


class LRU:
    # TODO: consider a more reasonable maxsize here
    def __init__(self, maxsize: int = 100000):
        self.maxsize = maxsize
        self.index: Dict[int, GenericNode] = collections.OrderedDict()

    def add(self, key: int, value: GenericNode) -> None:
        if len(self) == self.maxsize:
            self.pop()
        self.index[key] = value

    def pop(self) -> Tuple[int, GenericNode]:
        return self.index.popitem(last=True)  # type: ignore

    def get(
        self, key: int, default: Optional[GenericNode] = None
    ) -> Optional[GenericNode]:
        return self.index.get(key, default)

    def remove(self, key: int) -> None:
        del self.index[key]

    def add_head(self, key: int, value: GenericNode) -> None:
        if len(self) == self.maxsize:
            self.pop()

        # NOTE: check back to see if this is a costly operation
        new = collections.OrderedDict()
        new[key] = value
        new.update(self.index)
        self.index = new

    def items(self) -> List[Tuple[int, GenericNode]]:
        return list(self.index.items())

    def nodes(self) -> List[GenericNode]:
        # TODO: revisit way to get LRU head without having to call .nodes()
        return list(self.index.values())

    def head(self) -> GenericNode:
        return self.nodes()[0]

    def __len__(self) -> int:
        return len(self.index)

    def __contains__(self, node: GenericNode) -> bool:
        return node.long_id in self.index

    def __delitem__(self, node: GenericNode) -> None:
        if node in self:
            del self.index[node.long_id]

    def __str__(self) -> str:
        return str(self.index)


class KBucket:
    def __init__(self, lower_bound: float, upper_bound: float, ksize: int):
        self.range = (lower_bound, upper_bound)
        self.main_set = LRU()
        self.replacement_set = LRU()
        self.set_last_seen()
        self.ksize = ksize

    def set_last_seen(self) -> None:
        self.last_seen: float = time.monotonic()

    def get_set(self) -> List[GenericNode]:
        return self.main_set.nodes()

    def get_replacement_set(self) -> List[GenericNode]:
        """
		Section 4.1

		When we call_ping on head nodes in order to keep our LRU nodes
		fresh, if the head continues to respond, instead of throwing away
		the new node, we add its a replacement cache
		"""
        return self.replacement_set.nodes()

    def get_total_set(self) -> List[GenericNode]:
        all_nodes = []
        for n in self.get_set():
            all_nodes.append(n)

        for n in self.get_replacement_set():
            all_nodes.append(n)

        return all_nodes

    def split(self) -> Tuple["KBucket", "KBucket"]:
        midpoint = (self.range[0] + self.range[1]) / 2
        one = KBucket(self.range[0], midpoint, self.ksize)
        two = KBucket(midpoint + 1, self.range[1], self.ksize)
        nodes = chain(self.get_set(), self.get_replacement_set())

        for node in nodes:
            bucket = one if node.long_id <= midpoint else two
            bucket.add_node(node)
        return (one, two)

    def remove_node(self, node: GenericNode) -> None:
        if node in self.replacement_set:
            del self.replacement_set[node]

        if node in self.main_set:
            del self.main_set[node]

            if self.replacement_set:
                newnode_id, newnode = self.replacement_set.pop()
                self.main_set.add(newnode_id, newnode)

    def add_node(self, node: GenericNode) -> bool:
        """
		Section 4.1

		Add a C{GenericNode} to the C{KBucket}.  Return True if successful,
		False if the bucket is full. Using dict's ability to maintain order
		of items

		If the bucket is full, keep track of node in a replacement list,
		"""
        if node in self.main_set:
            del self.main_set[node]
            self.main_set.add(node.long_id, node)
            return True

        if len(self) < self.ksize:
            self.main_set.add(node.long_id, node)
            return True

        if node in self.replacement_set:
            del self.replacement_set[node]

        self.replacement_set.add(node.long_id, node)
        return False

    def depth(self) -> int:
        vals = self.main_set.nodes()
        sprefix = shared_prefix([bytes_to_bits(n.digest) for n in vals])
        return len(sprefix)

    def is_full(self) -> bool:
        return len(self) == self.ksize

    def head(self) -> GenericNode:
        return self.main_set.nodes()[0]

    def has_in_range(self, node: GenericNode) -> bool:
        return self.range[0] <= node.long_id <= self.range[1]

    def is_new_node(self, node: GenericNode) -> bool:
        return node not in self.main_set

    def total_nodes(self) -> int:
        return len(self.get_set()) + len(self.get_replacement_set())

    def __getitem__(self, node_id: int) -> Optional[GenericNode]:
        return self.main_set.get(node_id, None)

    def __len__(self) -> int:
        return len(self.main_set)


class RoutingTable:
    def __init__(self, protocol: TKademliaProtocol, ksize: int, node: GenericNode):
        """
		Section 2.4

		The routing table is a binary tree whose leaves are k-buckets, with
		each k-bucket being a leaf of the tree, containing nodes with a common
		prefix ID
		"""
        self.node = node
        self.protocol = protocol
        self.ksize = ksize
        self.maxlong: int = MAX_LONG
        self.flush()

    def flush(self) -> None:
        """ Each routing table starts with a single k-bucket """
        self.buckets: List[KBucket] = [KBucket(0, self.maxlong, self.ksize)]

    def split_bucket(self, index: int) -> None:
        one, two = self.buckets[index].split()
        self.buckets[index] = one
        self.buckets.insert(index + 1, two)

    def lonely_buckets(self) -> List[KBucket]:
        """
		Get all of the buckets that haven't been updated in over an hour.
		"""
        hrago = time.monotonic() - 3600
        return [b for b in self.buckets if b.last_seen < hrago and len(b) > 0]

    def remove_contact(self, node: GenericNode) -> None:
        """ Remove a node from its associated k-bucket """
        index = self.get_bucket_index_for(node)
        self.buckets[index].remove_node(node)

    def is_new_node(self, node: GenericNode) -> bool:
        """ Determine if the node's intended k-bucket already has the node """
        index = self.get_bucket_index_for(node)
        return self.buckets[index].is_new_node(node)

    def add_contact(self, node: GenericNode, attempted: bool = False) -> None:
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
                bucket.main_set.remove(bucket.head().long_id)
                bucket.main_set.add_head(node.long_id, node)
        return None

    def get_bucket_index_for(self, node: GenericNode) -> int:
        """
		Get the index of the bucket that the given node would fall into.
		"""
        for index, bucket in enumerate(self.buckets):
            if node.long_id < bucket.range[1]:
                return index
        # unreachable path needed for linter
        raise RuntimeError

    def find_neighbors(
        self,
        node: GenericNode,
        k: Optional[int] = None,
        exclude: Optional[GenericNode] = None,
    ) -> List[GenericNode]:

        k = k or self.ksize
        nodes: List[GenericNode] = []

        for neighbor in TableTraverser(self, node):
            notexcluded = exclude is None or not neighbor.is_same_node(exclude)
            if neighbor.long_id != node.long_id and notexcluded:
                heapq.heappush(nodes, (node.distance_to(neighbor), neighbor))  # type: ignore

            if len(nodes) == k:
                break

        return list(map(operator.itemgetter(1), heapq.nsmallest(k, nodes)))

    def num_buckets(self) -> int:
        return len(self.buckets)

    def num_nodes(self) -> int:
        return sum([len(b) for b in self.buckets])

    def total_nodes(self) -> int:
        return sum([b.total_nodes() for b in self.buckets])


class TableTraverser:
    def __init__(self, table: RoutingTable, start_node: GenericNode):
        index: int = table.get_bucket_index_for(start_node)
        table.buckets[index].set_last_seen()
        self.current_nodes = table.buckets[index].get_set()
        self.left_buckets = table.buckets[:index]
        self.right_buckets = table.buckets[(index + 1) :]
        self.left = True

    def __iter__(self) -> "TableTraverser":
        return self

    def __next__(self) -> GenericNode:
        """
		Pop an item from the left subtree, then right, then left, etc.
		"""
        if self.current_nodes:
            return self.current_nodes.pop()

        if self.left and self.left_buckets:
            self.current_nodes = self.left_buckets.pop().get_set()
            self.left = False
            return next(self)

        if self.right_buckets:
            self.current_nodes = self.right_buckets.pop(0).get_set()
            self.left = True
            return next(self)

        raise StopIteration
