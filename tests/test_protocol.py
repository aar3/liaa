import random
import asyncio
import time
import base64

import umsgpack

# pylint: disable=bad-continuation
from liaa.protocol import (
	KademliaProtocol, 
	RPCDatagramProtocol, 
	HttpInterface,
	Header
)
from liaa.storage import EphemeralStorage, StorageIface


class TestRPCDatagramProtocol:
	# pylint: disable=no-self-use
	loop = asyncio.get_event_loop()

	def test_can_instantiate(self, mkpeer):
		node = mkpeer()
		proto = RPCDatagramProtocol(node, wait=5)
		assert isinstance(proto, RPCDatagramProtocol)
		assert proto.source_node.key == node.key
		# assert len(proto._outstanding_msgs) == 0
		assert len(proto._queue) == 0

	def test_accept_request(self, mkpeer, mkdgram, sandbox):
		node = mkpeer()
		proto = RPCDatagramProtocol(node)

		box = sandbox(proto)

		def accept_request_stub(dgram):
			idf, data = dgram[1:21], umsgpack.unpackb(dgram[21:])
			funcname, args = data
			funcname = 'rpc_' + funcname
			return dgram[:1], funcname, args
		
		box.stub('_accept_request', accept_request_stub)

		header, funcname, data = proto._accept_request(mkdgram())
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
		msgargs = proto._accept_response(dgram, proto, address)
		assert msgargs[0] == base64.b64encode(dgram[1:21])
		assert msgargs[1] == address
		assert len(proto._queue) == 0

	def test_accept_response_returns_none_when_msg_not_outstanding(self, mkpeer, 
		mkdgram, sandbox):

		node = mkpeer()
		proto = RPCDatagramProtocol(node)
		dgram = mkdgram()
		result = proto._accept_response(dgram, ('127.0.0.1', 8000))
		assert not result

	def test_timeout_times_msg_out(self, mkpeer, mkdgram, sandbox):
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

	def test_call_store_stores(self, mkpeer):
		node = mkpeer()
		iface = HttpInterface(node, storage=StorageIface(node))
		response = iface.call_store('mykey', b'myvalue')
		assert response.startswith('HTTP/1.1 OK 200')
		assert response.endswith('{"details": "ok"}')

	def test_fetch_data_returns_none_when_key_not_exists(self, mkpeer, mkresource):
		node = mkpeer()
		iface = HttpInterface(node, storage=StorageIface(node))
		resource = mkresource('mykey', b'myvalue')
		response = iface.fetch_data('notexists')
		assert response.startswith('HTTP/1.1 NOT FOUND 404')
		assert response.endswith('{"details": "not found"}')

	def test_fetch_return_node_when_found(self, mkpeer, mkresource):
		node = mkpeer()
		iface = HttpInterface(node, storage=StorageIface(node))
		resource = mkresource('mykey', b'myvalue')
		iface.storage.set(resource)
		response = iface.fetch_data(resource.key)
		assert response.startswith('HTTP/1.1 OK 200')
		assert '"details": "found"' in response

class TestKademliaProtocol:
	# pylint: disable=no-self-use
	def test_can_init_protocol(self, mkpeer):
		node = mkpeer()
		proto = KademliaProtocol(node, storage=EphemeralStorage(node), ksize=20)
		assert isinstance(proto, KademliaProtocol)

	def test_can_refresh_ids(self, mkresource, mkbucket, fake_proto):
		proto = fake_proto()
		for _ in range(5):
			bucket = mkbucket(ksize=proto.router.ksize)
			for _ in range(5):
				node = mkresource()
				bucket.add_node(node)
			proto.router.add_bucket(bucket)

		# randomly pick some buckets to make stale
		sample = random.sample(proto.router.buckets, 3)
		for bucket in sample:
			bucket.last_updated = time.monotonic() - 3600

		to_refresh = proto.get_refresh_ids()
		assert isinstance(to_refresh, list)
		assert len(to_refresh) == 3

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
