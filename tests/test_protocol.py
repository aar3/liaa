# pylint: disable=protected-access

import random
import asyncio
import time
import base64
import itertools

import umsgpack

# pylint: disable=bad-continuation
from liaa.protocol import (
	KademliaProtocol,
	RPCDatagramProtocol,
	HttpInterface,
	Header
)
from liaa.routing import RoutingTable
from liaa.node import Node, ResourceNode, PeerNode
from liaa.storage import EphemeralStorage, StorageIface, IStorage


class TestRPCDatagramProtocol:
	# pylint: disable=no-self-use
	loop = asyncio.get_event_loop()

	def test_can_instantiate(self, mkpeer):
		node = mkpeer()
		proto = RPCDatagramProtocol(node, wait=5)
		assert isinstance(proto, RPCDatagramProtocol)
		assert proto.source_node.key == node.key
		# assert len(proto._outstanding_msgs) == 0

		# pylint: disable=protected-access
		assert len(proto._queue) == 0

	def test_accept_request(self, mkpeer, mkdgram, sandbox):
		node = mkpeer()
		proto = RPCDatagramProtocol(node)

		box = sandbox(proto)

		def accept_request_stub(dgram, address):
			_, data = dgram[1:21], umsgpack.unpackb(dgram[21:])
			funcname, args = data
			funcname = 'rpc_' + funcname
			return dgram[:1], funcname, args

		box.stub('_accept_request', accept_request_stub)

		header, funcname, data = proto._accept_request(mkdgram(), ('127.0.0.1', 8000))
		assert funcname == 'rpc_foo'
		assert header == Header.Request
		assert data == '12345'

	def test_accept_response(self, mkpeer, mkdgram, sandbox):
		node = mkpeer()
		proto = RPCDatagramProtocol(node)
		dgram = mkdgram()

		def timeout_fut(dgram):
			return self.loop.call_later(10, asyncio.sleep(10), dgram[1:21])

		proto._queue[dgram[1:21]] = (self.loop.create_future(), timeout_fut(dgram))

		assert len(proto._queue) == 1

		box = sandbox(proto)

		def accept_response_stub(dgram, proto, addr):
			idf, data = dgram[1:21], umsgpack.unpackb(dgram[21:])
			msgargs = (base64.b64encode(idf), addr)
			fut, timeout = proto._queue[idf]
			fut.set_result((True, data))
			timeout.cancel()
			del proto._queue[idf]
			return msgargs

		box.stub('_accept_response', accept_response_stub)

		address = ('127.0.0.1', 8000)
		msgid, address = proto._accept_response(dgram, proto, address)
		assert msgid == base64.b64encode(dgram[1:21])
		assert address == address
		assert len(proto._queue) == 0

	def test_accept_response_returns_empty(self, mkpeer, mkdgram):
		node = mkpeer()
		proto = RPCDatagramProtocol(node)
		dgram = mkdgram()

		result = proto._accept_response(dgram, ('127.0.0.1', 8000))
		assert not result

	def test_timeout_times_msg_out(self, mkpeer, mkdgram):
		node = mkpeer()
		proto = RPCDatagramProtocol(node)
		dgram = mkdgram()

		def timeout_fut(dgram):
			return self.loop.call_later(10, asyncio.sleep(10), dgram[1:21])

		proto._queue[dgram[1:21]] = (self.loop.create_future(), timeout_fut(dgram))
		proto._timeout(dgram[1:21])
		assert dgram[1:21] not in proto._queue



class TestHttpInterface:
	# pylint: disable=no-self-use
	def test_can_instantiate(self, mkpeer):
		node = mkpeer()
		iface = HttpInterface(node, storage=StorageIface(node))
		assert not iface.transport

	def test_call_store(self, mkpeer):
		node = mkpeer()
		iface = HttpInterface(node, storage=StorageIface(node))
		response = iface.call_store('mykey', b'myvalue')
		assert response.startswith('HTTP/1.1 OK 200')
		assert response.endswith('{"details": "ok"}')

	def test_fetch_data_returns_none(self, mkpeer):
		node = mkpeer()
		iface = HttpInterface(node, storage=StorageIface(node))
		response = iface.fetch_data('notexists')
		assert response.startswith('HTTP/1.1 NOT FOUND 404')
		assert response.endswith('{"details": "not found"}')

	def test_fetch_data_returns_data(self, mkpeer, mkresource):
		node = mkpeer()
		iface = HttpInterface(node, storage=StorageIface(node))
		resource = mkresource('mykey', b'myvalue')
		iface.storage.set(resource)
		response = iface.fetch_data(resource.key)
		assert response.startswith('HTTP/1.1 OK 200')
		assert '"details": "found"' in response


class TestKademliaProtocol:
	# pylint: disable=no-self-use
	def test_can_instantiate(self, mkpeer):
		node = mkpeer()
		proto = KademliaProtocol(node, storage=EphemeralStorage(node), ksize=20)
		assert isinstance(proto, KademliaProtocol)
		assert isinstance(proto.storage, IStorage)

	def test_can_get_refresh_ids(self, fake_proto, mknode):
		ksize = 3
		proto = fake_proto(ksize=ksize)
		# manually set maxlong and the node.long_id else get a memory error
		# because the MAX_LONG address space is so large, it will just keep
		# splitting buckets (as it should)
		proto.router = RoutingTable(proto, ksize, proto.source_node, maxlong=10)
		for x in range(4):
			node = mknode()
			node.long_id = x
			proto.router.add_contact(node)

		assert len(proto.router.buckets) == 3

		# randomly pick some buckets to make stale
		sample = random.sample(proto.router.buckets, 2)
		for bucket in sample:
			bucket.last_updated = time.monotonic() - 3600

		to_refresh = proto.get_refresh_ids()
		assert isinstance(to_refresh, list)
		assert len(to_refresh) > 0
		assert all([isinstance(n, Node) for n in to_refresh])

	def test_rpc_stun_returns_node(self, mkpeer, fake_proto):
		proto = fake_proto()
		sender = mkpeer()
		assert sender == proto.rpc_stun(sender)

	def test_rpc_ping_returns_requestors_id(self, mkpeer, fake_proto, sandbox):
		sender = mkpeer()
		proto = fake_proto()

		# pylint: disable=unused-argument
		def ping_stub(sender, node_id):
			return sender.key

		# pylint: disable=unused-argument
		def call_store_stub(node_to_ask, key, value):
			return True

		box = sandbox(proto)
		box.stub("call_store", call_store_stub)
		box.stub("rpc_ping", ping_stub)

		source_id = proto.rpc_ping(sender, sender.key)
		assert source_id == sender.key

		box.restore()

	def test_rpc_stores(self, mkpeer, fake_proto):
		sender = mkpeer()
		proto = fake_proto()

		success = proto.rpc_store((sender.ip, sender.port), sender.key, 'foo', b'bar')
		assert success

		# make sure
		result = proto.storage.get('foo')
		assert str(result) == 'resource@foo'

	def test_welcome_if_new_fails(self, fake_proto, sandbox, mknode, mkresource):

		def welcome_if_new_stub(proto, node):
			if not proto.router.is_new_node(node) or isinstance(node, ResourceNode):
				return
			for inode in proto.storage:
				neighbors = proto.router.find_neighbors(inode)
				if neighbors:
					furthest = neighbors[-1].distance_to(inode)
					is_closer_than_furthest = proto.distance_to(inode) < furthest
					closest_distance_to_new = neighbors[0].distance_to(inode)
					curr_distance_to_new = proto.source_node.distance_to(inode) < closest_distance_to_new
				if not neighbors or (is_closer_than_furthest and curr_distance_to_new):
					# here is where the call_store is stubbed
					return node, inode.key, inode.value
			proto.router.add_contact(node)

		# if node is not new node
		proto = fake_proto()
		box = sandbox(proto)
		node = mknode()
		box.stub('welcome_if_new', welcome_if_new_stub)
		proto.router.add_contact(node)
		assert not proto.welcome_if_new(proto, node)

		# if node is resource node
		proto = fake_proto()
		box = sandbox(proto)
		node = mkresource()
		box.stub('welcome_if_new', welcome_if_new_stub)
		assert not proto.welcome_if_new(proto, node)

	def test_welcome_if_new_adds(self, fake_proto, mkpeer, sandbox, mkresource):
		proto = fake_proto()
		box = sandbox(proto)

		def welcome_if_new_stub(proto, node):
			assert proto.router.is_new_node(node)
			if not proto.router.is_new_node(node) or isinstance(node, ResourceNode):
				return
			for inode in proto.storage:
				neighbors = proto.router.find_neighbors(inode)
				if neighbors:
					furthest = neighbors[-1].distance_to(inode)
					inode_closer_than_furthest = proto.source_node.distance_to(inode) < furthest
					closest_distance_to_new = neighbors[0].distance_to(inode)
					inode_dist_to_source_lt_new = proto.source_node.distance_to(inode) < closest_distance_to_new
				if not neighbors or (inode_closer_than_furthest and inode_dist_to_source_lt_new):
					# here is where the call_store is stubbed
					proto.router.add_contact(node)
					return node, inode.key, inode.value
			proto.router.add_contact(node)

		# make some nodes and add them to storage & router
		resources = [mkresource() for _ in range(3)]
		peers = [mkpeer() for _ in range(3)]
		nodes = list(itertools.chain(peers, resources))

		for node in nodes:
			proto.router.add_contact(node)

		for node in resources:
			proto.storage.set(node)

		assert len(proto.storage) == 3

		prevsize = proto.router.num_nodes()

		# add a new node that should have neighbors
		newnode = mkpeer()
		box.stub('welcome_if_new', welcome_if_new_stub)
		result = proto.welcome_if_new(proto, newnode)

		assert not result
		assert proto.router.num_nodes() == prevsize + 1

	def test_welcome_if_new_calls_store(self, fake_proto, mkpeer, sandbox, mkresource):
		proto = fake_proto()
		box = sandbox(proto)

		def welcome_if_new_stub(proto, node):
			assert proto.router.is_new_node(node)
			if not proto.router.is_new_node(node) or isinstance(node, ResourceNode):
				return
			for inode in proto.storage:
				neighbors = proto.router.find_neighbors(inode)
				if neighbors:
					furthest = neighbors[-1].distance_to(inode)
					inode_closer_than_furthest = proto.source_node.distance_to(inode) < furthest
					closest_distance_to_new = neighbors[0].distance_to(inode)
					inode_dist_to_source_lt_new = proto.source_node.distance_to(inode) < closest_distance_to_new
				if not neighbors or (inode_closer_than_furthest and inode_dist_to_source_lt_new):
					# here is where the call_store is stubbed
					proto.router.add_contact(node)
					return node, inode.key, inode.value
			proto.router.add_contact(node)

		# create some resources and add it one to storage
		resources = [mkresource() for _ in range(3)]
		proto.storage.set(resources[0])

		# a new peer should have no neighbors and call_store should be called
		newnode = mkpeer()
		box.stub('welcome_if_new', welcome_if_new_stub)
		prevsize = proto.router.num_nodes()
		(retnode, storekey, storeval) = proto.welcome_if_new(proto, newnode)

		assert retnode == newnode
		assert storekey == resources[0].key
		assert storeval == resources[0].value
		assert proto.router.num_nodes() == prevsize + 1

	def test_rpc_find_node_returns_neighbors(self, mknode, fake_proto, mkpeer):
		proto = fake_proto()
		nodes = [mknode() for _ in range(10)]
		for node in nodes:
			proto.router.add_contact(node)
		sender = mkpeer()
		result = proto.rpc_find_node(sender, sender.key, nodes[1].key)
		assert isinstance(result, list)
		assert len(result) == 9

	def test_rpc_find_node_returns_empty(self, fake_proto, mkpeer):
		proto = fake_proto()
		sender = mkpeer()
		result = proto.rpc_find_node(sender, sender.key, 'notAKey')
		assert len(result) == 0

	def test_rpc_find_value_returns_value(self, fake_proto, mkpeer, mkresource):
		proto = fake_proto()
		nodes = [mkresource() for _ in range(5)]
		for node in nodes:
			proto.storage.set(node)
		sender = mkpeer()
		result = proto.rpc_find_value(sender, sender.key, nodes[1].key)
		assert result['value'] == nodes[1]

	def test_find_value_return_empty(self, fake_proto, mkpeer):
		proto = fake_proto()
		sender = mkpeer()
		result = proto.rpc_find_value(sender, sender.key, 'notExists')
		assert result == []
