# pylint: disable=protected-access

import random
import asyncio
import time
import base64
import itertools

import umsgpack

from liaa.protocol import KademliaProtocol, RPCDatagramProtocol, Header
from liaa.routing import RoutingTable
from liaa.node import Node, IndexNode
from liaa.storage import EphemeralStorage


class TestRPCDatagramProtocol:
    loop = asyncio.get_event_loop()

    def test_can_init_proto(self, ping_node):
        node = ping_node()
        proto = RPCDatagramProtocol(node, wait=5)
        assert isinstance(proto, RPCDatagramProtocol)
        assert proto.source_node.key == node.key
        assert not proto.index

    def test_proto_can_accept_request(self, make_datagram, sandbox, make_proto):
        proto = make_proto()

        box = sandbox(proto)

        def accept_request_stub(dgram, _):
            _, data = dgram[1:21], umsgpack.unpackb(dgram[21:])
            funcname, args = data
            funcname = "rpc_" + funcname
            return dgram[:1], funcname, args

        box.stub("_accept_request", accept_request_stub)

        header, funcname, data = proto._accept_request(
            make_datagram(), ("127.0.0.1", 8000)
        )
        assert funcname == "rpc_foo"
        assert header == Header.Request
        assert data == "12345"

    def test_proto_can_accept_response_via_stub(
        self, make_datagram, make_proto, sandbox
    ):
        proto = make_proto()
        dgram = make_datagram()

        def timeout_fut(dgram):
            return self.loop.call_later(10, asyncio.sleep(10), dgram[1:21])

        proto.index[dgram[1:21]] = (self.loop.create_future(), timeout_fut(dgram))

        assert len(proto.index) == 1

        box = sandbox(proto)

        def accept_response_stub(dgram, proto, addr):
            idf, data = dgram[1:21], umsgpack.unpackb(dgram[21:])
            msgargs = (base64.b64encode(idf), addr)
            fut, timeout = proto.index[idf]
            fut.set_result((True, data))
            timeout.cancel()
            del proto.index[idf]
            return msgargs

        box.stub("_accept_response", accept_response_stub)

        address = ("127.0.0.1", 8000)

        msgid, addr = proto._accept_response(dgram, proto, address)
        assert msgid == base64.b64encode(dgram[1:21])
        assert addr == address
        assert not proto.index

    def test_proto_accept_response_returns_none_when_msg_id_not_in_proto_index(
        self, make_proto, make_datagram
    ):
        proto = make_proto()
        dgram = make_datagram()

        result = proto._accept_response(dgram, ("127.0.0.1", 8000))
        assert not result

    def test_proto_msg_timeout_removes_msg_from_index_when_msg_times_out(
        self, make_proto, make_datagram
    ):
        proto = make_proto()
        dgram = make_datagram()

        def timeout_fut(dgram):
            return self.loop.call_later(10, asyncio.sleep(10), dgram[1:21])

        proto.index[dgram[1:21]] = (self.loop.create_future(), timeout_fut(dgram))
        proto._timeout(dgram[1:21])
        assert dgram[1:21] not in proto.index


class TestKademliaProtocol:
    def test_can_init_proto(self, ping_node):
        node = ping_node()
        proto = KademliaProtocol(node, storage=EphemeralStorage(node), ksize=20)
        assert isinstance(proto, KademliaProtocol)
        assert isinstance(proto.storage, EphemeralStorage)

    def test_proto_can_get_refresh_ids_of_stale_buckets(self, make_proto, generic_node):
        ksize = 3
        proto = make_proto(ksize=ksize)
        proto.router = RoutingTable(proto, ksize, proto.source_node)

        for _ in range(4):
            node = generic_node()
            proto.router.add_contact(node)

        assert len(proto.router.buckets) == 2

        # randomly pick some buckets to make stale
        bucket = random.choice(proto.router.buckets)
        bucket.last_seen = time.monotonic() - 3601
        bucket_node_ids = [n.key for n in bucket.get_total_set()]

        refresh_bucket_ids = proto.get_refresh_ids()
        assert bucket_node_ids == refresh_bucket_ids

    def test_proto_rpc_stun_returns_same_sender_arg_that_was_passed(
        self, ping_node, make_proto
    ):
        proto = make_proto()
        sender = ping_node()
        assert sender == proto.rpc_stun(sender)

    def test_proto_rpc_ping_returns_requestors_id(self, ping_node, make_proto, sandbox):
        sender = ping_node()
        proto = make_proto()

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

    def test_proto_rpc_store_stores_a_give_key_value_pair(self, ping_node, make_proto):
        sender = ping_node()
        proto = make_proto()

        success = proto.rpc_store(sender, "foo", b"bar")
        assert success

        result = proto.storage.get("foo")

        assert result.key == "foo"
        assert result.value == b"bar"

    def test_welcome_if_new_fails(self, make_proto, sandbox, generic_node, index_node):
        def welcome_if_new_stub(proto, node):
            if not proto.router.is_new_node(node) or isinstance(node, IndexNode):
                return
            for inode in proto.storage:
                neighbors = proto.router.find_neighbors(inode)
                if neighbors:
                    furthest = neighbors[-1].distance_to(inode)
                    is_closer_than_furthest = proto.distance_to(inode) < furthest
                    closest_distance_to_new = neighbors[0].distance_to(inode)
                    curr_distance_to_new = (
                        proto.source_node.distance_to(inode) < closest_distance_to_new
                    )
                if not neighbors or (is_closer_than_furthest and curr_distance_to_new):
                    # here is where the call_store is stubbed
                    return node, inode.key, inode.value
            proto.router.add_contact(node)

        # if node is not new node
        proto = make_proto()
        box = sandbox(proto)
        node = generic_node()
        box.stub("welcome_if_new", welcome_if_new_stub)
        proto.router.add_contact(node)
        assert not proto.welcome_if_new(proto, node)

        # if node is resource node
        proto = make_proto()
        box = sandbox(proto)
        node = index_node()
        box.stub("welcome_if_new", welcome_if_new_stub)
        assert not proto.welcome_if_new(proto, node)

    def test_welcome_if_new_adds(self, make_proto, ping_node, sandbox, index_node):
        proto = make_proto()
        box = sandbox(proto)

        def welcome_if_new_stub(proto, node):
            assert proto.router.is_new_node(node)
            if not proto.router.is_new_node(node) or isinstance(node, IndexNode):
                return
            for inode in proto.storage:
                neighbors = proto.router.find_neighbors(inode)
                if neighbors:
                    furthest = neighbors[-1].distance_to(inode)
                    inode_closer_than_furthest = (
                        proto.source_node.distance_to(inode) < furthest
                    )
                    closest_distance_to_new = neighbors[0].distance_to(inode)
                    inode_dist_to_source_lt_new = (
                        proto.source_node.distance_to(inode) < closest_distance_to_new
                    )
                if not neighbors or (
                    inode_closer_than_furthest and inode_dist_to_source_lt_new
                ):
                    # here is where the call_store is stubbed
                    proto.router.add_contact(node)
                    return node, inode.key, inode.value
            proto.router.add_contact(node)

        # make some nodes and add them to storage & router
        resources = [index_node() for _ in range(3)]
        peers = [ping_node() for _ in range(3)]
        nodes = list(itertools.chain(peers, resources))

        for node in nodes:
            proto.router.add_contact(node)

        for node in resources:
            proto.storage.set(node)

        assert len(proto.storage) == 3

        prevsize = proto.router.total_nodes()

        # add a new node that should have neighbors
        newnode = ping_node()
        box.stub("welcome_if_new", welcome_if_new_stub)
        result = proto.welcome_if_new(proto, newnode)

        assert not result
        assert proto.router.total_nodes() == prevsize + 1

    def test_welcome_if_new_calls_store(
        self, make_proto, ping_node, sandbox, index_node
    ):
        proto = make_proto()
        box = sandbox(proto)

        def welcome_if_new_stub(proto, node):
            assert proto.router.is_new_node(node)
            if not proto.router.is_new_node(node) or isinstance(node, IndexNode):
                return
            for inode in proto.storage:
                neighbors = proto.router.find_neighbors(inode)
                if neighbors:
                    furthest = neighbors[-1].distance_to(inode)
                    inode_closer_than_furthest = (
                        proto.source_node.distance_to(inode) < furthest
                    )
                    closest_distance_to_new = neighbors[0].distance_to(inode)
                    inode_dist_to_source_lt_new = (
                        proto.source_node.distance_to(inode) < closest_distance_to_new
                    )
                if not neighbors or (
                    inode_closer_than_furthest and inode_dist_to_source_lt_new
                ):
                    # here is where the call_store is stubbed
                    proto.router.add_contact(node)
                    return node, inode.key, inode.value
            proto.router.add_contact(node)

        # create some resources and add it one to storage
        resources = [index_node() for _ in range(3)]
        proto.storage.set(resources[0])

        # a new peer should have no neighbors and call_store should be called
        newnode = ping_node()
        box.stub("welcome_if_new", welcome_if_new_stub)
        prevsize = proto.router.total_nodes()
        (retnode, storekey, storeval) = proto.welcome_if_new(proto, newnode)

        assert retnode == newnode
        assert storekey == resources[0].key
        assert storeval == resources[0].value
        assert proto.router.total_nodes() == prevsize + 1

    def test_rpc_find_node_returns_neighbors(self, generic_node, make_proto, ping_node):
        proto = make_proto()
        nodes = [generic_node() for _ in range(10)]
        for node in nodes:
            proto.router.add_contact(node)
        sender = ping_node()
        result = proto.rpc_find_node(sender, sender.key, nodes[1].key)
        assert isinstance(result, list)
        assert len(result) == 9

    def test_rpc_find_node_returns_empty(self, make_proto, ping_node):
        proto = make_proto()
        sender = ping_node()
        result = proto.rpc_find_node(sender, sender.key, "notAKey")
        assert not result

    def test_rpc_find_value_returns_value(self, make_proto, ping_node, index_node):
        proto = make_proto()
        nodes = [index_node() for _ in range(5)]
        for node in nodes:
            proto.storage.set(node)
        sender = ping_node()
        result = proto.rpc_find_value(sender, sender.key, nodes[1].key)
        assert list(result.values())[0] == nodes[1].value

    def test_find_value_return_empty(self, make_proto, ping_node):
        proto = make_proto()
        sender = ping_node()
        result = proto.rpc_find_value(sender, sender.key, "notExists")
        assert result == []
