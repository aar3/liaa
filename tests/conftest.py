# pylint: dangerous-default-value

import random
import umsgpack

import pytest

from liaa import MAX_LONG
from liaa.server import Server
from liaa.node import PingNode, IndexNode
from liaa.protocol import KademliaProtocol, Header
from liaa.routing import RoutingTable, KBucket, LRU
from liaa.storage import EphemeralStorage
from liaa.crawler import SpiderCrawl, ValueSpiderCrawl, NodeSpiderCrawl
from liaa.utils import rand_str


# pylint: disable=redefined-outer-name
@pytest.fixture()
def generic_node(ping_node, index_node):
    def _make_basic_node():
        """
		Make a node.  Created a random id if not specified.
		"""
        if random.choice([0, 1]) == 0:
            return ping_node()
        return index_node()

    return _make_basic_node


@pytest.fixture()
def ping_node():
    def _make_network_node(key=None):
        """
		Make a peer node.  Created a random id if not specified.
		"""
        key = key or "0.0.0.0:" + str(random.randint(1000, 9000))
        return PingNode(key)

    return _make_network_node


@pytest.fixture()
def make_lru():
    def _make_lru(maxsize=10):
        lru = LRU(maxsize=maxsize)
        items = [(x, str(x)) for x in range(5)]
        for key, val in items:
            lru.add(key, val)
        return lru

    return _make_lru


@pytest.fixture()
def index_node():
    def _make_storage_node(key=None, value=None):
        """
		Make a resource node.  Created a random id if not specified.
		"""
        key = key or rand_str(10)
        value = value or rand_str(10).encode("utf-8")
        return IndexNode(key, value)

    return _make_storage_node


@pytest.fixture()
def storage(ping_node):
    def _make_storage(ttl=5, node=None):
        node = node or ping_node()
        return EphemeralStorage(node, ttl)

    return _make_storage


@pytest.fixture()
def kbucket():
    def _make_kbucket(ksize, low=0, high=MAX_LONG):
        """
		Create a fake KBucket
		"""
        return KBucket(low, high, ksize)

    return _make_kbucket


# pylint: disable=too-few-public-methods
class FakeProtocol(KademliaProtocol):  # pylint: disable=too-few-public-methods
    def __init__(self, source_node, storage, ksize=20):
        super(FakeProtocol, self).__init__(source_node, storage, ksize)
        self.router = RoutingTable(self, ksize, source_node)


@pytest.fixture()
def make_proto(ping_node):
    def _make_proto(node=None, ksize=20):
        """
		Create a fake protocol
		"""
        node = node or ping_node()
        return FakeProtocol(node, EphemeralStorage(node), ksize=ksize)

    return _make_proto


@pytest.fixture()
def make_datagram():
    def _make_datagram(header=Header.Request, mid=None, args=None):
        """
		Create a fake datagram
		"""
        mid = mid or rand_str(20).encode()
        args = umsgpack.packb(args) if args else umsgpack.packb(("foo", "12345"))
        return header + mid + args

    return _make_datagram


# pylint: disable=too-few-public-methods
class FakeServer:
    def __init__(self, node):
        self.node = node
        self.storage = EphemeralStorage(node)
        self.ksize = 20
        self.alpha = 3
        self.protocol = FakeProtocol(self.node.key, self.storage, self.ksize)
        self.router = self.protocol.router


@pytest.fixture
def make_server(ping_node):
    return FakeServer(ping_node())


@pytest.fixture
def mkserver():
    def _mkserver(iface="0.0.0.0", port=8000):
        return Server(iface, port)

    return _mkserver


class Sandbox:
    def __init__(self, obj):
        self.obj = obj
        self.mem = {}

    def stub(self, funcname, func):
        self.mem[funcname] = getattr(self.obj, funcname)
        setattr(self.obj, funcname, func)

    def restore(self):
        for funcname, func in self.mem.items():
            setattr(self.obj, funcname, func)


@pytest.fixture
def sandbox():
    def _make_sandbox(obj=None):
        if not obj:
            raise RuntimeError("sandbox object cannot be None")
        return Sandbox(obj)

    return _make_sandbox


@pytest.fixture
def fake_spider_crawler(generic_node):
    def _make_fake_spider_crawler(node=None, peers=[]):
        node = node or generic_node()
        return SpiderCrawl(KademliaProtocol, node=node, peers=peers, ksize=3, alpha=3)

    return _make_fake_spider_crawler


@pytest.fixture
def fake_node_crawler(generic_node):
    def _make_fake_node_crawler(node=None, peers=[]):
        node = node or generic_node()
        return NodeSpiderCrawl(
            KademliaProtocol, node=node, peers=peers, ksize=3, alpha=3
        )

    return _make_fake_node_crawler


@pytest.fixture
def fake_value_crawler(generic_node):
    def _make_fake_value_crawler(node=None, peers=[]):
        node = node or generic_node()
        return ValueError(KademliaProtocol, node=node, peers=peers, ksize=3, alpha=3)

    return _make_fake_value_crawler
