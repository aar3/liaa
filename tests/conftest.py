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
from kademlia.node import Node
from kademlia.protocol import KademliaProtocol
from kademlia.routing import RoutingTable, KBucket
from kademlia.storage import ForgetfulStorage


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
	def _mknode(node_id=None, ip_addy=None, port=None, intid=None):
		"""
		Make a node.  Created a random id if not specified.
		"""
		if intid is not None:
			node_id = struct.pack('>l', intid)
		if not node_id:
			randbits = str(random.getrandbits(255))
			node_id = hashlib.sha1(randbits.encode()).digest()
		return Node(node_id, ip_addy, port)
	return _mknode


@pytest.fixture()
def mkdgram():
	def _mkdgram(header=Header.Request, msg_id=os.urandom(32), data=('funcname', 123)):
		buff = header + hashlib.sha1(msg_id).digest() + umsgpack.packb(data)
		return Datagram(buff)
	return _mkdgram


@pytest.fixture()
def mkqueue():
	def _mkqueue(msg_id=os.urandom(32), loop=loop):
		"""
		Create a fake RPCMessageQueue
		"""
		loop = asyncio.get_event_loop()
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
	def __init__(self, source_id, ksize=20):
		super(FakeProtocol, self).__init__(source_id, ksize=ksize)
		self.router = RoutingTable(self, ksize, Node(source_id))
		self.storage = ForgetfulStorage()
		self.source_id = source_id

@pytest.fixture()
def fake_proto(mknode):
	def _fake_proto(node=None):
		node = node or mknode()
		return FakeProtocol(node.id)
	return _fake_proto


# pylint: disable=too-few-public-methods
class FakeServer:
	def __init__(self, node_id):
		self.id = node_id  # pylint: disable=invalid-name
		self.protocol = FakeProtocol(self.id)
		self.router = self.protocol.router


@pytest.fixture
def fake_server(mknode):
	return FakeServer(mknode().id)
