import os
import random
import hashlib
import asyncio
import struct
import umsgpack

import pytest

# pylint: disable=bad-continuation
from kademlia.rpc import (
	RPCProtocol,
	RPCMessageQueue,
	Datagram,
	Header
)
from kademlia.network import Server
from kademlia.node import Node, NodeType
from kademlia.protocol import KademliaProtocol
from kademlia.routing import RoutingTable, KBucket
from kademlia.storage import EphemeralStorage
from kademlia.utils import rand_digest_id, rand_str


@pytest.yield_fixture
def bootstrap_node(event_loop):
	server = Server()
	event_loop.run_until_complete(server.listen(8468))

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
		buff = header + hashlib.sha1(msg_id).digest() + umsgpack.packb(data)
		return Datagram(buff)
	return _mkdgram


@pytest.fixture()
def mkrsrc():
	def _mkrsrc():
		"""
		Create a fake resource
		"""
		# pylint: disable=bad-continuation
		return Node(digest_id=rand_digest_id(),
						type=NodeType.Resource,
						value=rand_str().encode())
	return _mkrsrc

@pytest.fixture()
def mkqueue():
	def _mkqueue(msg_id=os.urandom(32)):
		"""
		Create a fake RPCMessageQueue
		"""
		loop = asyncio.new_event_loop()
		fut = loop.create_future()
		# pylint: disable=protected-access
		proto = RPCProtocol()
		timeout = loop.call_later(proto._wait, proto._timeout, msg_id)

		queue = RPCMessageQueue()
		queue.enqueue_fut(msg_id, fut, timeout)
		return queue
	return _mkqueue


# pylint: disable=too-few-public-methods
@pytest.fixture()
def mkbucket():
	def _mkbucket(ksize, low=0, high=2**160):
		return KBucket(low, high, ksize)
	return _mkbucket


# pylint: disable=too-few-public-methods
class FakeProtocol(KademliaProtocol):  # pylint: disable=too-few-public-methods
	def __init__(self, source_id, storage=EphemeralStorage(), ksize=20):
		super(FakeProtocol, self).__init__(source_id, storage=storage, ksize=ksize)
		self.router = RoutingTable(self, ksize, Node(source_id))
		self.source_id = source_id

@pytest.fixture()
def fake_proto(mknode):
	def _fake_proto(node=None):
		node = node or mknode()
		return FakeProtocol(node.digest_id)
	return _fake_proto


# pylint: disable=too-few-public-methods
class FakeServer:
	def __init__(self, node_id):
		self.id = node_id  # pylint: disable=invalid-name
		self.protocol = FakeProtocol(self.id)
		self.router = self.protocol.router


@pytest.fixture
def fake_server(mknode):
	return FakeServer(mknode().digest_id)


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
