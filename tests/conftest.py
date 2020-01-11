import os
import random
import hashlib
import struct
import umsgpack

import pytest

# pylint: disable=bad-continuation
from liaa.protocol import Header
from liaa.network import Server
from liaa.node import Node, NodeType
from liaa.protocol import KademliaProtocol
from liaa.routing import RoutingTable, KBucket
from liaa.storage import StorageIface
from liaa.utils import rand_digest_id, rand_str


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
	def _mknode(key=None, node_type=None, value=None):
		"""
		Make a node.  Created a random id if not specified.
		"""
		key = key or rand_str()
		node_type = node_type or NodeType.Peer
		return Node(key, node_type, value)
	return _mknode


@pytest.fixture()
def mkrsrc():
	def _mkrsrc(key=None, value=None):
		"""
		Create a fake resource node
		"""
		key = key or rand_str()
		value = value or rand_str()
		return Node(key=key, node_type=NodeType.Resource, value=value)
	return _mkrsrc


@pytest.fixture()
def mkbucket():
	def _mkbucket(ksize, low=0, high=2**160):
		"""
		Create a fake KBucket
		"""
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
		"""
		Create a fake protocol
		"""
		node = node or mknode()
		return FakeProtocol(node.digest, StorageIface(node), ksize=20)
	return _fake_proto


# pylint: disable=too-few-public-methods
class FakeServer:
	def __init__(self, node):
		self.node_id = node.digest
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
