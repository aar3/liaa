import pytest

from liaa import MAX_LONG
from liaa.node import Node, NodeHeap, PingNode, IndexNode
from liaa.utils import hex_to_int, pack


class TestNode:
    def test_peer_node(self):
        node = PingNode(key="127.0.0.1:8080")
        assert isinstance(node, PingNode)
        assert node.digest == pack(node.key)
        assert node.long_id < MAX_LONG
        assert str(node) == "PingNode@127.0.0.1:8080"

    def test_resource_node(self):
        node = IndexNode(key="my-node", value=b"123")
        assert isinstance(node, IndexNode)
        assert node.digest == pack(node.key)
        assert node.long_id < MAX_LONG
        assert str(node) == "IndexNode@my-node"

    def test_distance_calculation(self, ping_node):

        addr1 = "127.0.0.1:8000"
        addr2 = "127.0.0.1:9000"

        none = ping_node(key=addr1)
        ntwo = ping_node(key=addr2)

        shouldbe = hex_to_int(pack(addr1).hex()) ^ hex_to_int(pack(addr2).hex())

        assert none.distance_to(ntwo) == shouldbe

    def test_node_is_same_node(self, ping_node):
        node_one = node_two = ping_node()
        assert node_one.distance_to(node_two) == 0
        assert node_one.is_same_node(node_two)

    def test_node_iter_iterates_properties(self, ping_node):
        node = ping_node()
        ip, port = node.addr()
        assert tuple(node) == (node.key, ip, port)


class TestNodeHeap:
    def test_can_create_nodeheap(self, ping_node):
        heap = NodeHeap(ping_node(), 2)
        assert isinstance(heap, NodeHeap)

    def test_get_node_return_node_when_node_present(self, ping_node):
        heap = NodeHeap(ping_node(), 3)
        nodes = [ping_node() for _ in range(3)]
        for node in nodes:
            heap.push([node])
        node = heap.get_node(nodes[0].key)
        assert isinstance(node, Node)

    def test_get_node_returns_none_when_node_not_exists(self, ping_node):
        heap = NodeHeap(ping_node(), 1)
        empty = heap.get_node(123)
        assert not empty

    def test_mark_contacted_properly_labels_given_nodes(self, ping_node):
        maxsize = 10
        heap = NodeHeap(ping_node(), maxsize)
        nodes = [ping_node() for _ in range(maxsize)]
        for node in nodes:
            heap.push([node])
        contacted = nodes[:5]
        for node in contacted:
            heap.mark_contacted(node)

        assert len(heap.contacted) == 5
        assert not heap.has_exhausted_contacts()
        assert len(heap.get_uncontacted()) == 5

    def test_popleft_returns_left_if_heap_not_empty(self, ping_node):
        maxsize = 5
        heap = NodeHeap(ping_node(), maxsize)
        nodes = [ping_node() for _ in range(maxsize)]
        for node in nodes:
            heap.push([node])

        popped = heap.popleft()
        assert isinstance(popped, Node)

    def test_popleft_returns_none_when_heap_empty(self, ping_node):
        maxsize = 1
        heap = NodeHeap(ping_node(), maxsize)
        nodes = [ping_node()]
        for node in nodes:
            heap.push([node])

        heap.remove([nodes[0].key])

        popped = heap.popleft()
        assert not popped

    def test_heap_overload_doesnt_exceed_maxsize(self, ping_node):
        maxsize = 3
        heap = NodeHeap(ping_node(), maxsize)
        assert not heap

        for _ in range(10):
            heap.push([ping_node()])

        assert len(heap) == maxsize
        assert len(list(heap)) == maxsize

    def test_heap_iters_over_nsmallest_via_distance(self, ping_node):
        heap = NodeHeap(ping_node(), 5)
        nodes = [ping_node() for _ in range(10)]
        for node in nodes:
            heap.push([node])

        for index, node in enumerate(heap):
            assert index < 5

    @pytest.mark.skip(reason="this is not a good test - fix")
    def test_remove(self, ping_node):
        maxsize = 5
        heap = NodeHeap(ping_node(), maxsize)
        nodes = [ping_node() for _ in range(10)]
        for node in nodes:
            heap.push([node])

        heap.remove([nodes[0], nodes[1]])
        assert len(list(heap)) == maxsize

        for index, node in enumerate(heap):
            # we removed to elements so offset index to account for it
            assert index < maxsize
