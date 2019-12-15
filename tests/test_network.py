import os
import asyncio

from kademlia.network import Server, check_dht_value_type
from kademlia.protocol import KademliaProtocol


PORT = 8765

# @pytest.mark.asyncio
# async def test_storing(bootstrap_node):
# 	server = Server()
# 	await server.listen(bootstrap_node[1] + 1)
# 	await server.bootstrap([bootstrap_node])
# 	await server.set('key', 'value')
# 	result = await server.get('key')

# 	assert result == 'value'

# 	server.stop()


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
		dkey = os.urandom(16)
		server = Server()
		# pylint: disable=protected-access
		server.protocol = server._create_protocol()
		result = asyncio.run(server.set_digest(dkey, "foo"))
		assert not result


class TestServerUtils:
# pylint: disable=no-self-use
	def test_check_dht_value_type_returns_true_when_arg_is_valid(self):
		# pylint: disable=invalid-name
		a = check_dht_value_type("foo")
		assert a

		b = check_dht_value_type(8)
		assert b

		c = check_dht_value_type(b'123')
		assert c

		d = check_dht_value_type(True)
		assert d

		e = check_dht_value_type(3.14)
		assert e

		f = check_dht_value_type({})
		assert not f

		g = check_dht_value_type([])
		assert not g

		# pylint: disable=too-few-public-methods
		class Foo:
			pass

		h = check_dht_value_type(Foo())
		assert not h
