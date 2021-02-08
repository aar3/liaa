import os
import base64
import string
import random
import hashlib
import operator
import time
import asyncio
import collections
import heapq
import struct
import json
import umsgpack
import psutil
from _typing import *


BYTE_ORDER: str = "I"
MAX_LONG: int = 2 ** 125
KSIZE: int = 3

if os.environ.get("ENVIRONMENT") == "dev":
    MAX_LONG = 10
    KSIZE = 3


T = TypeVar("T")
TCacheKey = Union[str, int, T]
TAddress = Tuple[str, int]
TMessageFuture = Tuple[asyncio.Future, asyncio.Handle]


async def gather_coros(d):
    coros = list(d.values())
    results = await asyncio.gather(*coros)
    return dict(zip(d.keys(), results))


def to_addr(h: str, p: int) -> str:
    return h + ":" + str(p)


def hex_to_int(h: str) -> int:
    return int(h, 20)


def pack(s: str) -> bytes:
    b = s.encode()
    return struct.pack(BYTE_ORDER, len(b)) + b


def unpack(b: bytes) -> Any:
    size = struct.calcsize(BYTE_ORDER)
    return struct.unpack(BYTE_ORDER, b[:size]), b[size:]


def bytes_to_bits(b: bytes) -> str:
    return "".join([bin(bite)[2:].rjust(8, "0") for bite in b])


def shared_prefix(args: List[str]) -> str:
    i = 0
    while i < min(map(len, args)):
        if len(set(map(operator.itemgetter(i), args))) != 1:
            break
        i += 1
    return args[0][:i]


def random_string(n: int = 10) -> str:
    chars = list(string.ascii_letters + string.digits)
    return "".join([random.choice(chars) for _ in range(n)])


class BaseNode:
    def __init__(self, key: str):
        self.key = key
        self.digest = pack(self.key)
        self.payload: Dict[str, bytes] = {}
        self._long_id = hex_to_int(self.digest.hex())

    def distance_to(self, other) -> int:
        x: int = self.long_id ^ other.long_id
        return x

    @property
    def long_id(self) -> int:
        return self._long_id

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseNode):
            raise NotImplementedError
        return other.key == self.key

    def __iter__(self) -> Iterator[object]:
        return iter((self.long_id, self.key, self.payload))

    def serialize(self) -> str:
        raise NotImplementedError

    def __hash__(self) -> int:
        return self.long_id


class PeerNode(BaseNode):
    def set_payload(self, payload: Any):
        # payload can be a socket connection or what have out
        self.payload = payload

    @property
    def addr(self) -> Tuple[str, int]:
        host, port = self.key.split(":")
        return (host, int(port))

    def serialize(self) -> str:
        return json.dumps({"key": self.key, "long_id": self.long_id, "value": self.payload})


class CacheNode(BaseNode):
    def set_payload(self, payload: Dict[str, bytes] = {}):
        self.payload = payload

    def serialize(self) -> str:
        payload = list(self.payload.values())[0].decode()
        return json.dumps({"key": self.key, "long_id": self.long_id, "value": payload})


TNode = TypeVar("TNode", bound=BaseNode)
THashCacheKey = TypeVar("THashCacheKey", bound=Union[BaseNode, str, int])


def is_literal(x) -> bool:
    if isinstance(x, int) or isinstance(x, str):
        return True
    return False


class HashCache(Generic[T]):
    def __init__(self):
        # pylint: disable=unsubscriptable-object
        self.entries: collections.OrderedDict[Union[str, int], T] = collections.OrderedDict()

    @staticmethod
    def _extract_key(value: THashCacheKey, prop: str) -> Union[str, int]:
        if isinstance(value, str) or isinstance(value, int):
            return value
        key: Union[int, str] = getattr(value, prop, None)
        return key

    def add(self, item: T):
        self.entries[item.key] = item  # type: ignore

    def get(self, key: Union[str, int]) -> T:
        return self.entries[key]

    def items(self) -> List[T]:
        return list(self.entries.values())

    def remove(self, item: THashCacheKey):
        key = HashCache._extract_key(item, "key")
        del self.entries[key]

    def popitem(self, last: bool) -> T:
        _, value = self.entries.popitem(last=last)
        return value

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Generator[T, None, None]:
        for _, entry in self.entries.items():
            yield entry

    def __contains__(self, item: THashCacheKey) -> bool:
        key = HashCache._extract_key(item, "key")
        return key in self.entries


class NodeHeap(Generic[TNode]):
    def __init__(self, source_node: TNode, max_size: int):
        self.source_node = source_node
        self.heap: List[Tuple[int, TNode]] = []
        self.contacted: Set[TNode] = set()
        self.max_size = max_size

    def push(self, nodes: List[TNode] = []):
        while nodes:
            node = nodes.pop()
            if node not in self:
                distance = self.source_node.distance_to(node)
                heapq.heappush(self.heap, (distance, node))

    def remove(self, nodes: List[str]):
        if not nodes:
            return
        node_heap: List[Tuple[int, TNode]] = []
        for distance, node in self.heap:
            if node not in nodes:
                heapq.heappush(node_heap, (distance, node))
        self.heap = node_heap

    def has_exhausted_contacts(self) -> bool:
        return len(self.uncontacted()) == 0

    def uncontacted(self) -> List[TNode]:
        return [n for n in self if n not in self.contacted]

    def mark_contacted(self, node: TNode):
        self.contacted.add(node)

    def ids(self) -> Set[str]:
        return set([node.key for node in map(operator.itemgetter(1), self.heap)])

    def __len__(self) -> int:
        return min(len(self.heap), self.max_size)

    def __iter__(self):
        nodes = heapq.nsmallest(self.max_size, self.heap)
        return iter(map(operator.itemgetter(1), nodes))

    def __contains__(self, n: TNode) -> bool:
        for _, other in self.heap:
            if n == other:
                return True
        return False


class KBucket(Generic[TNode]):
    def __init__(self, start: float, end: float, ksize: int):
        self.start = start
        self.end = end
        self.range = (self.start, self.end)
        self.ksize = ksize
        self.main_set: HashCache[TNode] = HashCache()
        self.replacement_set: HashCache[TNode] = HashCache()
        self.set_last_seen()

    @property
    def head(self) -> TNode:
        return self.main_set.items()[0]

    def has_nodes(self) -> bool:
        return len(self) > 0

    def is_full(self) -> bool:
        return len(self) == self.ksize

    def is_new_node(self, n: TNode) -> bool:
        return n not in self.main_set

    def set_last_seen(self):
        self.last_seen = time.monotonic()

    def get_main_set(self):
        return self.main_set.items()

    def get_replacement_set(self) -> List[Any]:
        return self.replacement_set.items()

    def get_aggregate_set(self) -> List[TNode]:
        return self.main_set.items() + self.replacement_set.items()

    def split(self) -> Tuple["KBucket", "KBucket"]:
        midpoint = (self.range[0] + self.range[1]) / 2
        one: KBucket = KBucket(self.range[0], midpoint, self.ksize)
        two: KBucket = KBucket(midpoint + 1, self.range[1], self.ksize)

        for node in self.main_set.items() + self.replacement_set.items():
            bucket = one if node.long_id <= midpoint else two
            bucket.add_node(node)

        return (one, two)

    def remove_node(self, node: TNode):
        if node in self.main_set:
            self.main_set.remove(node)

            if self.replacement_set:
                new_node = self.replacement_set.popitem(last=True)
                self.main_set.add(new_node)
                return None

        if node in self.replacement_set:
            self.replacement_set.remove(node)

        return None

    def add_node(self, node: TNode) -> bool:
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

    def has_in_range(self, n: TNode) -> bool:
        return self.range[0] <= n.long_id <= self.range[1]

    def depth(self) -> int:
        return len(shared_prefix([bytes_to_bits(node.digest) for node in self.main_set]))

    def __len__(self) -> int:
        return len(self.main_set)


class RoutingTable:
    def __init__(self, protocol, ksize: int, source_node: TNode, max_long: int = MAX_LONG):
        self.protocol = protocol
        self.ksize = ksize
        self.buckets: List[KBucket[TNode]] = []
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
        return [b for b in self.buckets if b.last_seen < hr_ago and b.has_nodes()]

    def remove_node(self, n: TNode):
        index = self.get_bucket_index(n)
        self.buckets[index].remove_node(n)

    def is_new_node(self, n: TNode) -> bool:
        index = self.get_bucket_index(n)
        return self.buckets[index].is_new_node(n)

    def get_bucket_index(self, node: TNode) -> int:
        for index, bucket in enumerate(self.buckets):
            if node.long_id < bucket.range[1]:
                return index
        raise NotImplementedError

    def add_node(self, n: TNode, attempted: bool = False):
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
        index = self.get_bucket_index(n)
        bucket = self.buckets[index]
        bucket.set_last_seen()

        if bucket.is_full() and attempted:
            return

        if bucket.add_node(n):
            return

        if bucket.has_in_range(self.source_node) or bucket.depth() % 5 != 0:
            self.split_bucket(index)
            return self.add_node(n, True)

        if bucket.is_full():
            result = asyncio.ensure_future(self.protocol.call_ping(bucket.head))
            if not result:
                bucket.main_set.remove(bucket.head.long_id)
                bucket.main_set.add(n)
        return

    def find_neighbors(self, n: TNode, k: Optional[int] = None, exclude: Optional[TNode] = None) -> List[TNode]:
        k = k or self.ksize
        nodes: List[TNode] = []

        for neighbor in TableTraverser(self, n):
            not_excluded = exclude is None or not neighbor.is_same_node(exclude)
            if not_excluded:
                heapq.heappush(nodes, (n.distance_to(neighbor), neighbor))  # type: ignore

            if len(nodes) == k:
                break

        return list(map(operator.itemgetter(1), heapq.nsmallest(k, nodes)))

    def count_of_nodes_in_table(self) -> int:
        return sum([len(b) for b in self.buckets])


class TableTraverser:
    def __init__(self, table: RoutingTable, start_node: TNode):
        start_index: int = table.get_bucket_index(start_node)
        table.buckets[start_index].set_last_seen()
        self.curr_nodes: List[TNode] = table.buckets[start_index].get_main_set()
        self.left_buckets = table.buckets[:start_index]
        self.right_buckets = table.buckets[start_index:]
        self.left = True

    def __iter__(self):
        return self

    def __next__(self) -> TNode:
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


class Datagram:
    MIN_MSG_SIZE = 22

    def __init__(self, sender: Tuple[str, int], data: bytes):
        self.sender = sender
        if len(data) < Datagram.MIN_MSG_SIZE:
            self._malformed = True
        else:
            self.data = data
            self.id, (self.rpc_method_name, self.args) = (
                data[1:21],
                umsgpack.unpackb(data[21:]),
            )
            self.rpc_method = getattr(self, f"rpc_{self.rpc_method_name}", None)
            self._malformed = False
        self.payload: Optional[TMessageFuture] = None

    @property
    def malformed(self) -> bool:
        return self._malformed

    @property
    def key(self) -> str:
        return self.id.decode()

    def set_payload(self, payload: TMessageFuture):
        self.payload = payload

    async def exec_rpc_method(self, rpc_method):
        return rpc_method(self.sender, *self.args)

    def end_fut(self, data: bytes):
        if not self.payload:
            return

        fut, timeout = self.payload
        fut.set_result((True, data))
        timeout.cancel()

    def set_fut_result(self):
        fut, _ = self.payload
        fut.set_result((False, None))


class TDatagramProtocol(asyncio.DatagramProtocol):
    REQUEST: bytes
    RESPONSE: bytes
    MIN_MSG_SIZE: int
    MAX_RPC_METHOD_SIZE: int


class RPCDatagramProtocol(TDatagramProtocol):

    REQEUST = b"\x00"
    RESPONSE = b"\x01"
    MIN_MSG_SIZE = 22
    MAX_RPC_METHOD_SIZE = 8192

    def __init__(self, source_node: PeerNode, wait: int = 5):
        self.source_node = source_node
        self.wait = wait
        self.msg_cache: HashCache[Datagram] = HashCache()
        self.transport: Optional[asyncio.BaseTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        asyncio.ensure_future(self._solve_datagram(data, addr))

    def _solve_datagram(self, data: bytes, addr: Tuple[str, int]):
        if len(data) < RPCDatagramProtocol.MIN_MSG_SIZE:
            return

        if data[0] == RPCDatagramProtocol.REQUEST:
            self._accept_request(data, addr)

        elif data[0] == RPCDatagramProtocol.RESPONSE:
            self._accept_response(data, addr)

        else:
            return

    async def _accept_request(self, data: bytes, addr: Tuple[str, int]):
        msg = Datagram(addr, data)
        rpc_method = getattr(self, f"rpc_{msg.rpc_method_name}", None)

        criteria = [
            (not rpc_method, "rpc_method not found in protocol"),
            (not callable(rpc_method), "rpc_method not callable"),
            (
                not asyncio.iscoroutinefunction(rpc_method),
                "rpc_method is not a coroutine",
            ),
        ]

        for criterium, msg in criteria:  # type: ignore
            if criterium:
                print(msg)
                return

        # FIXME: Do you need to pass rpc_method *args here too?
        rpc_result = await msg.exec_rpc_method(rpc_method)
        response = RPCDatagramProtocol.RESPONSE + msg.id + umsgpack.packb(rpc_result)

        self.transport.sendto(response, addr)  # type: ignore

    async def _accept_response(self, data: bytes, addr: Tuple[str, int]):
        # FIXME: Should we do something with data here as in request? For the most part
        # a request and a response are the same thing
        msg_id, data = data[1:21], umsgpack.unpackb(data[21:])
        id_as_str = msg_id.decode()
        msg_args = (base64.b64encode(msg_id), addr)

        if not id_as_str in self.msg_cache:
            return

        msg = self.msg_cache.get(id_as_str)
        msg.end_fut(data)

        self.msg_cache.remove(id_as_str)

    def time_msg_out(self, msg_id: bytes):
        """
        A speed and size optimization used to keep cache clean by removing
        stale futures (requests with no responses and visa versa)
        """
        # args = (base64.b64encode(msg_id), self.wait)
        msg_id_str = msg_id.decode()
        if not msg_id_str in self.msg_cache:
            return

        msg: Datagram = self.msg_cache.get(msg_id.decode())

        msg.set_fut_result()
        self.msg_cache.remove(msg.id.decode())

    def __getattr__(self, name: str):

        if name.startswith("_") or name.startswith("rpc_"):
            return getattr(super(), name)

        try:
            return getattr(super(), name)
        except AttributeError:
            pass

        def build_dgram(addr: Tuple[str, int], rpc_args):
            rpc_method_name = name
            msg_id = hashlib.sha1(os.urandom(32)).digest()
            data = umsgpack.packb([rpc_method_name, rpc_args])

            if len(data) > RPCDatagramProtocol.MAX_RPC_METHOD_SIZE:
                return

            request = RPCDatagramProtocol.REQUEST + msg_id + data
            self.transport.sendto(request, addr)  # type: ignore

            loop = asyncio.get_event_loop()
            fut = loop.create_future()
            timeout = loop.call_later(self.wait, self.time_msg_out, msg_id)
            msg = Datagram(self.source_node.addr, data=request)
            msg.set_payload((fut, timeout))
            self.msg_cache.add(msg)

        return build_dgram


class CacheStorage(Generic[T]):
    def __init__(self, max_items: int = 10, max_space: int = 100_000):
        self.max_items = max_items
        self.max_space = max_space
        self.cache: Dict[Union[str, int], T] = {}

    def get(self, key: Union[str, int]) -> Optional[T]:
        return self.cache.get(key)

    def set(self, key: Union[str, int], value: T):
        self.cache[key] = value

    def add_node(self, node: CacheNode) -> int:
        self.cache[node.long_id] = node  # type: ignore
        return 1

    def remove(self, key: Union[str, int]):
        if key in self.cache:
            del self.cache[key]

    def has_capacity(self) -> bool:
        return len(self.cache) < self.max_items and self._memory_usage() < self.max_space

    def _memory_usage(self) -> int:
        process = psutil.Process(os.getpid())
        x: int = process.memory_info().rss
        return x

    def __iter__(self) -> Generator[T, None, None]:
        for _, node in self.cache.items():
            yield node


class RPCContainer:
    def __init__(self, protocol: "KademliaProtocol"):
        self.protocol = protocol

    def store(self, requestor: PeerNode, payload: CacheNode):
        raise NotImplementedError

    def rpc_stun(self, sender: PeerNode) -> PeerNode:
        return sender

    def rpc_ping(self, sender: PeerNode) -> PeerNode:
        self.welcome_node_if_new(sender)
        return self.protocol.source_node

    def rpc_store(self, sender: PeerNode, key: str, value: bytes):
        self.welcome_node_if_new(sender)
        self.protocol.storage.set(key, value)

    def rpc_find_node(self, sender: PeerNode, to_find: TNode) -> List[TAddress]:
        self.welcome_node_if_new(sender)
        neighbors = self.protocol.router.find_neighbors(to_find, exclude=self.protocol.source_node)  # type: ignore
        peers = list(filter(lambda n: isinstance(n, PeerNode), neighbors))
        return list(map(tuple, peers))  # type: ignore

    def rpc_find_value(self, sender: PeerNode, value_node: TNode) -> CacheNode:
        self.welcome_node_if_new(sender)
        found_node = self.protocol.storage.get(value_node.long_id)
        if not found_node:
            self.rpc_find_node(sender, value_node)
        return found_node  # type: ignore

    def welcome_node_if_new(self, node: PeerNode):
        """
        Section 2.5

        Given a new node (Peer), send it all the keys/values it should be storing,
        then add it to the routing table.

        Process:

        For each key in storage, get k closest nodes.  If newnode is closer
        than the furtherst in that list, and the node for this server
        is closer than the closest in that list, then store the key/value
        on the new node
        """
        if not self.protocol.router.is_new_node(node):
            return

        if not isinstance(node, PeerNode):
            raise TypeError("welcome_node_if_new called with non-PeerNode")

        for node_ in self.protocol.storage:
            neighbors = self.protocol.router.find_neighbors(node_)
            if neighbors:
                furthest = neighbors[-1].distance_to(node_)
                is_closer_than_furthest = node.distance_to(node_) < furthest
                closest_distance_to_new = neighbors[0].distance_to(node_)
                curr_is_closer = self.protocol.source_node.distance_to(node_) < closest_distance_to_new

            if not neighbors or (is_closer_than_furthest and curr_is_closer):
                asyncio.ensure_future(self.call_store(node, node_))

        self.protocol.router.add_node(node)

    async def call_store(self, requestee: PeerNode, payload: CacheNode):
        result = await self.store(requestee, payload)
        return self.handle_call_response(result, requestee)

    def handle_call_response(self, result, sender):
        raise NotImplementedError


TNodeAsTuple = Tuple[int, str, Any]


class KademliaProtocol(RPCDatagramProtocol, RPCContainer):
    def __init__(self, source_node: PeerNode, storage: CacheStorage, ksize: int, wait: int):
        super(KademliaProtocol, self).__init__(source_node, wait)
        self.router = RoutingTable(self, ksize, source_node)
        self.storage = storage
        self.ksize = ksize

    """
    FIXME

    The rpc_* methods must return raw values instead of abstractions
    They can be bubble up into abstractions later if need be
    But the rpc_* methods are the ones that go over the wire, so they need raw values
    """

    def get_refreshable_nodes(self) -> List[TNode]:
        nodes = []
        for bucket in self.router.lonely_buckets():
            n: TNode = random.choice(bucket.main_set.items())
            nodes.append(n)
        return nodes

    def rpc_stun(self, sender: PeerNode) -> PeerNode:
        return sender

    def rpc_ping(self, sender: PeerNode) -> PeerNode:
        self.welcome_node_if_new(sender)
        return self.source_node

    def rpc_store(self, sender: PeerNode, to_store: CacheNode):
        self.welcome_node_if_new(sender)
        self.storage.add_node(to_store)

    def rpc_find_node(self, sender: PeerNode, to_find: TNode) -> List[TAddress]:
        self.welcome_node_if_new(sender)
        neighbors = self.router.find_neighbors(to_find, exclude=sender)  # type: ignore
        return list(map(tuple, neighbors))  # type: ignore

    def rpc_find_value(self, sender: PeerNode, value_node: TNode) -> CacheNode:
        self.welcome_node_if_new(sender)
        result = self.storage.get(value_node.long_id)
        if result is None:
            return self.rpc_find_value(self.source_node, value_node)
        return result

    async def call_find_node(self, to_find: TNode) -> List[TNodeAsTuple]:
        neighbors = await self.find_node(self.source_node, to_find)
        return self.handle_call_response(neighbors, self.source_node)

    def handle_call_response(self, result: List[TNodeAsTuple], sender: PeerNode):
        if not result:
            return self.router.remove_node(sender)
        return result


class Server:
    def __init__(self, interface: str, port: int, ksize: int = 20, alpha: int = 3):
        self.node = PeerNode(key=to_addr(interface, port))
        self.storage: CacheStorage = CacheStorage()
        self.ksize = ksize
        self.alpha = alpha
        self.refresh_interval = 60
        self.state = "./node.state"

        self.udp_transport = None
        self.protocol = KademliaProtocol(self.node, self.storage, self.ksize, wait=5)
        self.refresh_loop = None
        self.save_state_loop = None
        self.listener = None

    def stop(self):
        if self.udp_transport is not None:
            self.udp_transport.close()

        if self.refresh_loop:
            self.refresh_loop.cancel()

        if self.save_state_loop:
            self.save_state_loop.cancel()

        if self.listener:
            asyncio.ensure_future(self.listener.wait_closed())

    def bootstrap_neighbors(self, addrs: List[str]):
        neighbors = self.protocol.find_neighbors(self.node)
        return []

    async def bootstrap(self, addrs: Tuple[str, int]):
        coros = list(map(self.bootstrap_node, addrs))  # type: ignore
        neighbors = await asyncio.gather(*coros)
        neighbors = filter(lambda x: x is not None, neighbors)
        spider = NodeSpiderCrawler(self.protocol, self.node, neighbors, self.ksize, self.alpha)
        return spider.find()

    def bootstrap_node(self, node: PeerNode) -> PeerNode:
        return self.protocol.ping(node)

    def get(self, key: str):
        result = self.storage.get(key)
        if result is not None:
            return result

        node = CacheNode(key)
        nearest = self.protocol.router.find_neighbors(node)

        if not nearest:
            logger.info(json.dumps({
                "caller": self.__class__.__name__,
                "ts": time.time(),
                "details": f"{self.source_node.key} has no known neighbors for {key}"
                }))
            return

        spider = ValueSpiderCrawler(self.protocol, node, nearest, self.ksize, self.alpha)
        return spider.find()

    def set(self, key: str, value: bytes) -> bool:
        node = CacheNode(key, value)
        return self.store(node)

    async def store(self, node: CacheNode): -> bool:
        nearest = self.protocol.router.find_neighbors(node)
        if not nearest:
            logger.info(json.dumps({
                "caller": self.__class__.__name__,
                "ts": time.time(),
                "details": f"{self.source_node.key} has no known neighbors with which to share {node.key}"
                }))
            return 

        spider = NodeSpiderCrawler(self.protocol, node, nearest, self.ksize, self.alpha)
        found = await spider.find()
        furthest = max([n.distance_to(node) for n in found])
        if self.source_node.distance_to(node) < furthest:
            self.storage.add_node(node)

        coros = [self.protocol.call_store(n, node) for n in found]
        return any(await asyncio.gather(*coros))

    def save_state(self):
        state = {
            "addr": to_addr((self.interface, self.port)),
            "ksize": self.ksize,
            "alpha": self.alpha,
            "id": self.source_node.key,
            # FIXME: make sure this returns something serializable
            "neighbors": self.bootstrapable_neighbors()
        }

        ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(f"./state/{self.source_node.key}.{ts}.txt", "wb") as f:
            pickle.dump(data, f)

        return 
            

    def load_state(self):
        data = {}
        with open(f"./state/{self.source_node.key}.{ts}.txt", "rb") as f:
            data = pickle.load(f)

        server = Server(**data)
        asyncio.ensure_future(self.bootstra(data["neighbors"]))
        return server

    def save_state_loop(self, frequency: int = 60):
        self.save_state()
        loop = asyncio.get_event_loop()
        self.save_state_loop = loop.call_later(frequency, self.save_state_loop)


class SpiderCrawler:
    def __init__(self, protocol: KademliaProtocol, start_node: TNode, neighbors: List[TNode], ksize: int, alpha: int):
        self.protocol = protocol
        self.start_node = start_node
        self.ksize = ksize
        self.alpha = alpha
        self.nearest = NodeHeap[TNode](self.start_node, self.ksize)
        self.last_ids_crawled: Set[str] = set()
        self.nearest.push(neighbors)

    async def _find(self, rpc_method):
        count = self.alpha
        nearest_ids = self.nearest.ids()
        if nearest_ids == self.last_ids_crawled:
            count = len(self.nearest)

        coros = {}

        self.last_ids_crawled = nearest_ids
        for node in self.nearest.uncontacted()[:count]:
            if isinstance(node, CacheNode):
                continue

            # FIXME: are any of these async?
            # FIXME: notice how we call the rpc_method with the node abstraction here
            coros[node.key] = rpc_method(node, self.start_node)
            self.nearest.mark_contacted(node)

        coros_response = await gather_coros(coros)
        return self._parse_rpc_results(coros_response)

    async def _parse_rpc_results(self, coros_response):
        raise NotImplementedError


class RawRPCResponse:
    def __init__(self, items: Dict[str, Optional[TNodeAsTuple]]):
        self.items = items

    def did_happen(self):
        return 


class NodeSpiderCrawler(SpiderCrawler):
    def _parse_rpc_results(self, responses):
        to_remove = []
        for node_id, node in response.items():
            



    def find(self):
        return self._find(self.protocol.call_find_node)  

