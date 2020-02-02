import os
import random
import hashlib
import struct
import umsgpack

import pytest

from liaa import MAX_LONG
from liaa.server import Server
from liaa.node import Node, PeerNode, ResourceNode
from liaa.protocol import KademliaProtocol, Header
from liaa.routing import RoutingTable, KBucket, LRUCache
from liaa.storage import StorageIface
from liaa.utils import rand_str


# pylint: disable=redefined-outer-name
@pytest.fixture()
def mknode(mkpeer, mkresource):
	def _mknode():
		"""
		Make a node.  Created a random id if not specified.
		"""
		if random.choice([0, 1]) == 0:
			return mkpeer()
		return mkresource()
	return _mknode

@pytest.fixture()
def mkpeer():
	def _mkpeer(key=None):
		"""
		Make a peer node.  Created a random id if not specified.
		"""
		key = key or f"127.0.0.1:{random.randint(1000, 9000)}"
		return PeerNode(key)
	return _mkpeer


@pytest.fixture()
def mklru():
	def _mklru(maxsize=10):
		cache = LRUCache(maxsize=maxsize)
		items = [(x, str(x)) for x in range(5)]
		for key, val in items:
			cache[key] = val
		return cache
	return _mklru


@pytest.fixture()
def mkresource():
	def _mkresource(key=None, value=None):
		"""
		Make a resource node.  Created a random id if not specified.
		"""
		key = key or rand_str()
		return ResourceNode(key, value)
	return _mkresource


@pytest.fixture()
def mkbucket():
	def _mkbucket(ksize, low=0, high=MAX_LONG):
		"""
		Create a fake KBucket
		"""
		return KBucket(low, high, ksize)
	return _mkbucket


# pylint: disable=too-few-public-methods
class FakeProtocol(KademliaProtocol):  # pylint: disable=too-few-public-methods
	def __init__(self, source_node, storage, ksize=20):
		super(FakeProtocol, self).__init__(source_node, storage, ksize)
		self.router = RoutingTable(self, ksize, source_node)


@pytest.fixture()
def fake_proto(mkpeer):
	def _fake_proto(node=None, ksize=None):
		"""
		Create a fake protocol
		"""
		node = node or mkpeer()
		ksize = ksize or 20
		return FakeProtocol(node, StorageIface(node), ksize=ksize)
	return _fake_proto


@pytest.fixture()
def mkdgram():
	def _mkdgram(header=None, mid=None, args=None):
		"""
		Create a fake datagram
		"""
		header = header or Header.Request
		mid = mid or rand_str(20).encode()
		args = umsgpack.packb(args) if args else umsgpack.packb(('foo', '12345'))
		return header + mid + args
	return _mkdgram


# pylint: disable=too-few-public-methods
class FakeServer:
	def __init__(self, node):
		self.node = node
		self.storage = StorageIface(node)
		self.ksize = 20
		self.alpha = 3
		self.protocol = FakeProtocol(self.node.key, self.storage, self.ksize)
		self.router = self.protocol.router


@pytest.fixture
def fake_server(mkpeer):
	return FakeServer(mkpeer())


@pytest.fixture
def mkserver():
	def _mkserver(iface=None, port=None, ksize=None, alpha=None):
		iface = iface or "0.0.0.0"
		port = port or 8000
		srv = Server(iface, port)
		# pylint: disable=protected-access
		srv._create_protocol()
		return srv
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
	def _sandbox(obj=None):
		if not obj:
			raise RuntimeError("sandbox object cannot be None")
		return Sandbox(obj)
	return _sandbox
