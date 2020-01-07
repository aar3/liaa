import asyncio
import os

from kademlia.network import Server
from kademlia.protocol import KademliaProtocol
# from kademlia.node import Resource
from kademlia.node import Node, NodeType
from kademlia.utils import rand_str, rand_digest_id


PORT = 8765


class TestServer:
	# pylint: disable=no-self-use
	def test_server_instance_is_ok(self):
		server = Server()
		assert isinstance(server, Server)

	def test_server_can_start_and_stop(self):
		loop = asyncio.get_event_loop()
		server = Server()

		assert not server.udp_transport
		assert not server.protocol
		assert not server.refresh_loop
		assert not server.save_state_loop
		assert not server.listener

		loop.run_until_complete(server.listen(PORT))

		assert server.udp_transport
		assert server.protocol
		assert isinstance(server.refresh_loop, asyncio.Handle)
		assert isinstance(server.protocol, KademliaProtocol)
		assert isinstance(server.listener, asyncio.AbstractServer)

		server.stop()

		# assert server.udp_transport.closed()
		assert server.refresh_loop.cancelled()
		assert server.save_state_loop.cancelled()
		# assert not server.listener.is_serving()

	def test_create_protocol_is_interchangeable(self):
		server = Server()
		# pylint: disable=protected-access
		proto = server._create_protocol()
		assert isinstance(proto, KademliaProtocol)

		class CoconutProtocol(KademliaProtocol):
			pass

		class HuskServer(Server):
			protocol_class = CoconutProtocol
		husk_server = HuskServer()
		assert isinstance(husk_server._create_protocol(), CoconutProtocol)


	def test_set_digest_returns_void_when_node_has_no_neighbors(self):
		server = Server()
		resource = Node(rand_digest_id(), type=NodeType.Resource, value=rand_str())
		# pylint: disable=protected-access
		server.protocol = server._create_protocol()
		result = asyncio.run(server.set_digest(resource))
		assert not result

	def test_save_state_saves(self, sandbox, mknode):
		server = Server()

		# pylint: disable=unused-argument,bad-continuation
		def bootstrappable_neighbors_stub():
			return [
				mknode(digest_id=rand_digest_id(), ip="0.0.0.0", port=1234),
				mknode(digest_id=rand_digest_id(), ip="0.0.0.0", port=4321)
			]

		box = sandbox(server)
		box.stub("bootstrappable_neighbors", bootstrappable_neighbors_stub)

		server.save_state()

		expected_path = os.path.join(server.storage.dir, "node.state")
		assert os.path.exists(expected_path)
		assert os.path.isfile(expected_path)

		box.restore()

	def test_can_load_state(self, sandbox, mknode):
		server = Server()
		asyncio.set_event_loop(asyncio.new_event_loop())
		# pylint: disable=unused-argument,bad-continuation
		def bootstrappable_neighbors_stub():
			return [
				# make some fake peers
				mknode(digest_id=rand_digest_id(), ip="0.0.0.0", port=1234),
				mknode(digest_id=rand_digest_id(), ip="0.0.0.0", port=4321)
			]

		def bootstrap_stub(addrs):
			return addrs

		box = sandbox(server)
		box.stub("bootstrappable_neighbors", bootstrappable_neighbors_stub)
		box.stub("bootstrap", bootstrap_stub)

		server.save_state()
		loaded_server = server.load_state()
		assert isinstance(loaded_server, Server)

		box.restore()
