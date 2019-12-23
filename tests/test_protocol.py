import asyncio
import random
import time

# pylint: disable=bad-continuation
from kademlia.rpc import RPCMessageQueue, Datagram
from kademlia.protocol import KademliaProtocol
from kademlia.storage import ForgetfulStorage


class TestRPCMessageQueue:
	# pylint: disable=no-self-use
	def test_can_instantiate_queue(self):
		queue = RPCMessageQueue()
		assert isinstance(queue, RPCMessageQueue)

	def test_can_enqueue_item(self, mkqueue):
		queue = mkqueue()
		assert len(queue) == 1

	def test_can_get_fut(self, mkqueue, mkdgram):
		dgram = mkdgram()
		queue = mkqueue(dgram.id)
		fut, timeout = queue.get_fut(dgram.id)
		assert isinstance(fut, asyncio.Future)
		assert isinstance(timeout, asyncio.Handle)

	def test_contains_return_true_if_msg_id_found(self, mkqueue, mkdgram):
		dgram = mkdgram()
		queue = mkqueue(dgram.id)
		assert dgram.id in queue

	def test_dequeue_returns_true_when_dequeued(self, mkqueue, mkdgram):
		dgram = mkdgram()
		queue = mkqueue(dgram.id)
		assert queue.dequeue_fut(dgram)


class TestDatagram:
	# pylint: disable=no-self-use
	def test_can_init_dgram(self, mkdgram):
		assert isinstance(mkdgram(), Datagram)

	def test_dgram_has_valid_len(self, mkdgram):
		dgram = mkdgram()
		assert dgram.has_valid_len()

	def test_is_malformed_is_false(self, mkdgram):
		dgram = mkdgram()
		assert not dgram.is_malformed()

	def test_is_malformed_is_true(self, mkdgram):
		dgram = mkdgram(data="123")
		assert dgram.is_malformed()



class TestKademliaProtocol:
	# pylint: disable=no-self-use
	def test_can_init_protocol(self, mknode):
		node = mknode(intid=1)
		proto = KademliaProtocol(node, ksize=20)
		proto.storage = ForgetfulStorage()
		assert isinstance(proto, KademliaProtocol)

	def test_can_refresh_ids(self, mknode, mkbucket, fake_proto):
		proto = fake_proto()
		for _ in range(5):
			bucket = mkbucket(ksize=proto.router.ksize)
			for _ in range(5):
				node = mknode()
				bucket.add_node(node)
			proto.router.add_bucket(bucket)

		# randomly pick some buckets to make stale
		sample = random.sample(proto.router.buckets, 3)
		for bucket in sample:
			bucket.last_updated = time.monotonic() - 3600

		to_refresh = proto.get_refresh_ids()
		assert isinstance(to_refresh, list)
		assert len(to_refresh) == 3

	def test_rpc_stun_returns_node(self, mknode, fake_proto):
		proto = fake_proto()
		sender = mknode()
		assert sender == proto.rpc_stun(sender)

	def test_rpc_ping_returns_requestors_id(self, mknode, fake_proto, sandbox):
		sender = mknode()
		proto = fake_proto()

		# pylint: disable=unused-argument
		def ping_stub(sender, node_id):
			return sender.id

		# pylint: disable=unused-argument
		def call_store_stub(node_to_ask, key, value):
			return True

		box = sandbox(proto)
		box.stub("call_store", call_store_stub)
		box.stub("rpc_ping", ping_stub)

		source_id = proto.rpc_ping(sender, sender.id)
		assert source_id == sender.id

		box.restore()
