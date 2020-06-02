import asyncio
import os

from liaa.server import Server
from liaa.protocol import KademliaProtocol


class TestServer:

    loop = asyncio.get_event_loop()

    def test_can_instantiate(self):
        server = Server("0.0.0.0", 8000)
        assert isinstance(server, Server)
        # assert server.node.ip == "0.0.0.0"
        # assert server.node.port == 8000

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

    def test_set_digest_with_no_neighbors(self, mkserver, index_node):
        server = mkserver()
        node = index_node()
        # pylint: disable=protected-access
        server.protocol = server._create_protocol()
        result = self.loop.run_until_complete(server.set_digest(node))
        assert not result

    def test_save_state(self, sandbox, mkserver, ping_node):
        server = mkserver()

        # pylint: disable=unused-argument,bad-continuation
        def bootstrappable_neighbors_stub():
            return [ping_node(), ping_node()]

        box = sandbox(server)
        box.stub("bootstrappable_neighbors", bootstrappable_neighbors_stub)

        server.save_state()

        expected_path = os.path.join(server.storage.dir, "node.state")
        assert os.path.exists(expected_path)
        assert os.path.isfile(expected_path)

        box.restore()

    def test_load_state(self, mkserver, sandbox, ping_node):
        server = mkserver()
        asyncio.set_event_loop(asyncio.new_event_loop())

        def bootstrappable_neighbors_stub():
            return [ping_node(), ping_node()]

        def bootstrap_stub(addrs):
            return addrs

        box = sandbox(server)
        box.stub("bootstrappable_neighbors", bootstrappable_neighbors_stub)
        box.stub("bootstrap", bootstrap_stub)

        server.save_state()
        loaded_server = server.load_state()
        assert isinstance(loaded_server, Server)

        box.restore()
