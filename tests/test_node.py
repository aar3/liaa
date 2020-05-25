from liaa import MAX_LONG
from liaa.node import Node, NodeHeap, NetworkNode, StorageNode
from liaa.utils import hex_to_int, pack


class TestNode:
    def test_peer_node(self):
        node = NetworkNode(key="127.0.0.1:8080")
        assert isinstance(node, NetworkNode)
        assert node.ip == "127.0.0.1"
        assert node.port == 8080
        assert node.digest == pack(node.key)
        assert node.long_id < MAX_LONG
        assert str(node) == "NetworkNode@127.0.0.1:8080"

    def test_resource_node(self):
        node = StorageNode(key="my-node", value=b"123")
        assert isinstance(node, StorageNode)
        assert node.digest == pack(node.key)
        assert node.long_id < MAX_LONG
        assert str(node) == "StorageNode@my-node"

    def test_distance_calculation(self, make_network_node):

        addr1 = "127.0.0.1:8000"
        addr2 = "127.0.0.1:9000"

        none = make_network_node(key=addr1)
        ntwo = make_network_node(key=addr2)

        shouldbe = hex_to_int(pack(addr1).hex()) ^ hex_to_int(pack(addr2).hex())

        assert none.distance_to(ntwo) == shouldbe

    def test_node_is_same_node(self, make_network_node):
        node_one = node_two = make_network_node()
        assert node_one.distance_to(node_two) == 0
        assert node_one.is_same_node(node_two)

    def test_node_iter(self, make_network_node):
        node = make_network_node()
        assert tuple(node) == (node.key, node.ip, node.port)


class TestNodeHeap:
    def test_can_create_nodeheap(self, make_network_node):
        heap = NodeHeap(make_network_node(), 2)
        assert isinstance(heap, NodeHeap)

    def test_get_node_return_node_when_node_present(self, make_network_node):
        heap = NodeHeap(make_network_node(), 3)
        nodes = [make_network_node() for _ in range(3)]
        for node in nodes:
            heap.push([node])
        node = heap.get_node(nodes[0].key)
        assert isinstance(node, Node)

    def test_get_node_returns_none_when_node_not_exists(self, make_network_node):
        heap = NodeHeap(make_network_node(), 1)
        empty = heap.get_node(123)
        assert not empty

    def test_mark_contacted_works_ok(self, make_network_node):
        maxsize = 10
        heap = NodeHeap(make_network_node(), maxsize)
        nodes = [make_network_node() for _ in range(maxsize)]
        for node in nodes:
            heap.push([node])
        contacted = nodes[:5]
        for node in contacted:
            heap.mark_contacted(node)

        assert len(heap.contacted) == 5
        assert not heap.have_contacted_all()
        assert len(heap.get_uncontacted()) == 5

    def test_popleft_returns_left_if_heap_not_empty(self, make_network_node):
        maxsize = 5
        heap = NodeHeap(make_network_node(), maxsize)
        nodes = [make_network_node() for _ in range(maxsize)]
        for node in nodes:
            heap.push([node])

        popped = heap.popleft()
        assert isinstance(popped, Node)

    def test_popleft_returns_none_when_heap_empty(self, make_network_node):
        maxsize = 1
        heap = NodeHeap(make_network_node(), maxsize)
        nodes = [make_network_node()]
        for node in nodes:
            heap.push([node])

        heap.remove(nodes)

        popped = heap.popleft()
        assert not popped

    def test_heap_overload_doesnt_exceed_maxsize(self, make_network_node):
        maxsize = 3
        heap = NodeHeap(make_network_node(), maxsize)
        assert not heap

        for _ in range(10):
            heap.push([make_network_node()])

        assert len(heap) == maxsize
        assert len(list(heap)) == maxsize

    def test_heap_iters_over_nsmallest_via_distance(self, make_network_node):
        heap = NodeHeap(make_network_node(), 5)
        nodes = [make_network_node() for _ in range(10)]
        for node in nodes:
            heap.push([node])

        for index, node in enumerate(heap):
            assert index < 5

    def test_remove(self, make_network_node):
        maxsize = 5
        heap = NodeHeap(make_network_node(), maxsize)
        nodes = [make_network_node() for _ in range(10)]
        for node in nodes:
            heap.push([node])

        heap.remove([nodes[0], nodes[1]])
        assert len(list(heap)) == maxsize

        for index, node in enumerate(heap):
            # we removed to elements so offset index to account for it
            assert index < maxsize
