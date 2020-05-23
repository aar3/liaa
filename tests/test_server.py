import asyncio
import os

from liaa.server import Server
from liaa.protocol import KademliaProtocol, HttpInterface
from liaa.storage import StorageIface


class TestServer:

    loop = asyncio.get_event_loop()

    # pylint: disable=no-self-use
    def test_can_instantiate(self):
        server = Server("0.0.0.0", 8000)
        assert isinstance(server, Server)
        assert server.node.ip == "0.0.0.0"
        assert server.node.port == 8000

    def test_can_start_and_stop(self, mkserver):
        server = mkserver()

        assert not server.udp_transport
        assert not server.protocol
        assert not server.refresh_loop
        assert not server.save_state_loop
        assert not server.listener

        self.loop.run_until_complete(server.listen())

        assert server.udp_transport
        assert server.protocol
        assert isinstance(server.refresh_loop, asyncio.Handle)
        assert isinstance(server.protocol, KademliaProtocol)
        assert isinstance(server.listener, asyncio.AbstractServer)

        server.stop()

        assert server.refresh_loop.cancelled()
        assert server.save_state_loop.cancelled()

    def test_protocol_change(self, mkserver):
        server = mkserver()
        # pylint: disable=protected-access
        proto = server._create_protocol()
        assert isinstance(proto, KademliaProtocol)

        class CoconutProtocol(KademliaProtocol):
            pass

        class HuskServer(Server):
            protocol_class = CoconutProtocol

        husk_server = HuskServer("0.0.0.0", 9000)
        assert isinstance(husk_server._create_protocol(), CoconutProtocol)

    def test_set_digest_with_no_neighbors(self, mkserver, make_storage_node):
        server = mkserver()
        node = make_storage_node()
        # pylint: disable=protected-access
        server.protocol = server._create_protocol()
        result = self.loop.run_until_complete(server.set_digest(node))
        assert not result

    def test_save_state(self, make_sandbox, mkserver, make_network_node):
        server = mkserver()

        # pylint: disable=unused-argument,bad-continuation
        def bootstrappable_neighbors_stub():
            return [make_network_node(), make_network_node()]

        box = make_sandbox(server)
        box.stub("bootstrappable_neighbors", bootstrappable_neighbors_stub)

        server.save_state()

        expected_path = os.path.join(server.storage.dir, "node.state")
        assert os.path.exists(expected_path)
        assert os.path.isfile(expected_path)

        box.restore()

    def test_load_state(self, mkserver, make_sandbox, make_network_node):
        server = mkserver()
        asyncio.set_event_loop(asyncio.new_event_loop())

        def bootstrappable_neighbors_stub():
            return [make_network_node(), make_network_node()]

        def bootstrap_stub(addrs):
            return addrs

        box = make_sandbox(server)
        box.stub("bootstrappable_neighbors", bootstrappable_neighbors_stub)
        box.stub("bootstrap", bootstrap_stub)

        server.save_state()
        loaded_server = server.load_state()
        assert isinstance(loaded_server, Server)

        box.restore()


class TestHttpInterface:
    # pylint: disable=no-self-use
    def test_can_instantiate(self, make_network_node):
        node = make_network_node()
        iface = HttpInterface(node, storage=StorageIface(node))
        assert not iface.transport

    def test_call_store(self, make_network_node):
        node = make_network_node()
        iface = HttpInterface(node, storage=StorageIface(node))
        response = iface.call_store("mykey", b"myvalue")
        assert response.startswith("HTTP/1.1 OK 200")
        assert response.endswith('{"details": "ok"}')

    def test_fetch_data_returns_none(self, make_network_node):
        node = make_network_node()
        iface = HttpInterface(node, storage=StorageIface(node))
        response = iface.fetch_data("notexists")
        assert response.startswith("HTTP/1.1 NOT FOUND 404")
        assert response.endswith('{"details": "not found"}')

    def test_fetch_data_returns_data(self, make_network_node, make_storage_node):
        node = make_network_node()
        iface = HttpInterface(node, storage=StorageIface(node))
        resource = make_storage_node("mykey", b"myvalue")
        iface.storage.set(resource)
        response = iface.fetch_data(resource.key)
        assert response.startswith("HTTP/1.1 OK 200")
        assert '"details": "found"' in response
