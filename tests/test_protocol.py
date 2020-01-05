import random
import time

from kademlia.protocol import KademliaProtocol
from kademlia.storage import EphemeralStorage


class TestKademliaProtocol:
	# pylint: disable=no-self-use
	def test_can_init_protocol(self, mknode):
		node = mknode(intid=1)
		proto = KademliaProtocol(node, storage=EphemeralStorage(node), ksize=20)
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
			return sender.digest_id

		# pylint: disable=unused-argument
		def call_store_stub(node_to_ask, key, value):
			return True

		box = sandbox(proto)
		box.stub("call_store", call_store_stub)
		box.stub("rpc_ping", ping_stub)

		source_id = proto.rpc_ping(sender, sender.digest_id)
		assert source_id == sender.digest_id

		box.restore()
