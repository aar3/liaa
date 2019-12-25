import os
import asyncio

from kademlia.network import Server
from kademlia.protocol import KademliaProtocol
from kademlia.node import Resource
from kademlia.utils import rand_id


PORT = 8765


class TestServer:
	# pylint: disable=no-self-use
	def test_server_instance_is_ok(self):
		server = Server()
		assert isinstance(server, Server)

	def test_server_can_stop_ok(self):
		loop = asyncio.get_event_loop()
		server = Server()
		loop.run_until_complete(server.listen(PORT))
		assert not server.refresh_loop.cancelled()
		server.stop()
		assert server.refresh_loop.cancelled()

	def test_server_listen_initializes_ok(self):
		loop = asyncio.get_event_loop()
		server = Server()

		assert not server.transport
		assert not server.protocol
		assert not server.refresh_loop
		assert not server.protocol

		# listen() should intialize instance attributes
		loop.run_until_complete(server.listen(PORT))

		assert server.transport
		assert server.protocol
		assert isinstance(server.refresh_loop, asyncio.Handle)
		assert isinstance(server.protocol, KademliaProtocol)

		server.stop()

	def test_create_protocol_returns_protocol(self):
		server = Server()
		# pylint: disable=protected-access
		proto = server._create_protocol()
		assert isinstance(proto, KademliaProtocol)

	def test_server_can_use_custom_protocol(self):

		# Make a custom Protocol and Server to go with it
		class CoconutProtocol(KademliaProtocol):
			pass

		class HuskServer(Server):
			protocol_class = CoconutProtocol

		# An ordinary server does NOT have a CoconutProtocol as its protocol...
		loop = asyncio.get_event_loop()
		server = Server()
		loop.run_until_complete(server.listen(PORT))
		assert not isinstance(server.protocol, CoconutProtocol)
		server.stop()

		# ...but our custom server does.
		husk_server = HuskServer()
		loop.run_until_complete(husk_server.listen(PORT))
		assert isinstance(husk_server.protocol, CoconutProtocol)
		husk_server.stop()

	def test_set_digest_returns_void_when_node_has_no_neighbors(self):
		server = Server()
		# pylint: disable=protected-access
		rsrc = Resource(key=rand_id(), value=rand_id())
		server.protocol = server._create_protocol()
		result = asyncio.run(server.set_digest(rsrc))
		assert not result
