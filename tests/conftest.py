import os
import random
import hashlib
import asyncio
import struct
import umsgpack

import pytest

# pylint: disable=bad-continuation
from kademlia.protocol import RPCDatagramProtocol, Header
from kademlia.network import Server
from kademlia.node import Node, NodeType
from kademlia.protocol import KademliaProtocol
from kademlia.routing import RoutingTable, KBucket
from kademlia.storage import StorageIface
from kademlia.utils import rand_digest_id, rand_str


@pytest.yield_fixture
def bootstrap_node(event_loop):
	server = Server()
	event_loop.run_until_complete(server.listen_udp(8468))

	try:
		yield ('127.0.0.1', 8468)
	finally:
		server.stop()

# pylint: disable=redefined-outer-name
@pytest.fixture()
def mknode():
	def _mknode(digest_id=None, ip_addy=None, port=None, intid=None):
		"""
		Make a node.  Created a random id if not specified.
		"""
		if intid is not None:
			digest_id = struct.pack('>l', intid)
		if not digest_id:
			randbits = str(random.getrandbits(255))
			digest_id = hashlib.sha1(randbits.encode()).digest()
		return Node(digest_id, ip_addy, port)
	return _mknode


@pytest.fixture()
def mkdgram():
	def _mkdgram(header=Header.Request, msg_id=os.urandom(32), data=('funcname', 123)):
		"""
		Create a datagram
		"""
		return header + hashlib.sha1(msg_id).digest() + umsgpack.packb(data)
	return _mkdgram


@pytest.fixture()
def mkrsrc():
	def _mkrsrc(key=None, value=None):
		"""
		Create a fake resource
		"""
		key = key or rand_digest_id()
		value = value or rand_str()
		# pylint: disable=bad-continuation
		return Node(digest_id=key,
						type=NodeType.Resource,
						value=value)
	return _mkrsrc


# pylint: disable=too-few-public-methods
@pytest.fixture()
def mkbucket():
	def _mkbucket(ksize, low=0, high=2**160):
		return KBucket(low, high, ksize)
	return _mkbucket


# pylint: disable=too-few-public-methods
class FakeProtocol(KademliaProtocol):  # pylint: disable=too-few-public-methods
	def __init__(self, source_id, storage, ksize=20):
		super(FakeProtocol, self).__init__(source_id, storage=storage, ksize=ksize)
		self.router = RoutingTable(self, ksize, Node(source_id))
		self.source_id = source_id


@pytest.fixture()
def fake_proto(mknode):
	def _fake_proto(node=None):
		node = node or mknode()
		return FakeProtocol(node.digest_id, StorageIface(node), ksize=20)
	return _fake_proto


# pylint: disable=too-few-public-methods
class FakeServer:
	def __init__(self, node):
		self.node_id = node.digest_id
		self.storage = StorageIface(node)
		self.ksize = 20
		self.alpha = 3
		self.protocol = FakeProtocol(self.node_id, self.storage, self.ksize)
		self.router = self.protocol.router


@pytest.fixture
def fake_server(mknode):
	return FakeServer(mknode())


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
