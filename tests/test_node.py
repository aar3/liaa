import random
import hashlib
from collections.abc import Iterable

from liaa.node import Node, NodeHeap, NodeType
from liaa.utils import hex_to_int, pack


class TestNode:
	# pylint: disable=no-self-use
	def test_node_instance_attributes(self):
		node = Node(key="127.0.0.1:8080", node_type=NodeType.Peer)

		assert node.ip == "127.0.0.1"
		assert node.port == 8080
		assert node.node_type == NodeType.Peer
		assert not node.value

		assert isinstance(node.long_id, int)
		assert isinstance(node.digest, bytes)
		assert node.digest == pack("I", node.key)
		assert node.long_id < 2**160

		assert str(node) == "peer@127.0.0.1:8080"

	def test_distance_calculation(self):

		addr1 = "127.0.0.1:8000"
		addr2 = "127.0.0.1:9000"

		none = Node(key=addr1, node_type=NodeType.Peer)
		ntwo = Node(key=addr2, node_type=NodeType.Peer)

		shouldbe = hex_to_int(pack("I", addr1).hex()) ^ hex_to_int(pack("I", addr2).hex())

		assert none.distance_to(ntwo) == shouldbe

	def test_distance_calc_for_same_node(self, mknode):
		addr = "127.0.0.1:8000"
		node_one = mknode(key=addr, node_type=NodeType.Peer)
		node_two = mknode(key=addr, node_type=NodeType.Peer)
		assert node_one.distance_to(node_two) == 0

	def test_is_same_node(self, mknode):
		addr = "127.0.0.1:8000"
		node_one = mknode(key=addr, node_type=NodeType.Peer)
		node_two = mknode(key=addr, node_type=NodeType.Peer)
		assert node_one.is_same_node(node_two)

	def test_node_iter(self, mknode):
		addr = "127.0.0.1:8000"
		node = mknode(key=addr, node_type=NodeType.Peer)
		assert tuple(node) == (node.digest, node.ip, node.port)


class TestNodeHeap:
	# pylint: disable=no-self-use
	def test_can_create_nodeheap(self, mknode):
		heap = NodeHeap(mknode(key="0:0", node_type=NodeType.Peer), 2)
		assert isinstance(heap, NodeHeap)

	def test_get_node_return_node_when_node_present(self, mknode):
		heap = NodeHeap(mknode(key="0:0", node_type=NodeType.Peer), 3)
		nodes = [mknode(key="0:1", node_type=NodeType.Peer) for i in range(3)]
		for node in nodes:
			heap.push(node)
		node = heap.get_node(nodes[0].digest)
		assert isinstance(node, Node)

	def test_get_node_returns_none_when_node_not_exists(self, mknode):
		heap = NodeHeap(mknode(key="0:0", node_type=NodeType.Peer), 1)
		empty = heap.get_node(123)
		assert not empty

	def test_mark_contacted_works_ok(self, mknode):
		maxsize = 10
		heap = NodeHeap(mknode(key="0:0", node_type=NodeType.Peer), maxsize)
		nodes = [mknode(key=f"0:{x}", node_type=NodeType.Peer) for x in range(maxsize)]
		for node in nodes:
			heap.push(node)
		contacted = nodes[:5]
		for node in contacted:
			heap.mark_contacted(node)

		assert len(heap.contacted) == 5
		assert not heap.have_contacted_all()
		assert len(heap.get_uncontacted()) == 5

	def test_popleft_returns_left_if_heap_not_empty(self, mknode):
		maxsize = 5
		heap = NodeHeap(mknode(key="0:0", node_type=NodeType.Peer), maxsize)
		nodes = [mknode(key=f"0:{x}", node_type=NodeType.Peer) for x in range(maxsize)]
		for node in nodes:
			heap.push(node)

		popped = heap.popleft()
		assert isinstance(popped, Node)

	def test_popleft_returns_none_when_heap_empty(self, mknode):
		maxsize = 1
		heap = NodeHeap(mknode(key="0:0", node_type=NodeType.Peer), maxsize)
		nodes = [mknode(key="0:1", node_type=NodeType.Peer)]
		for node in nodes:
			heap.push(node)

		heap.remove(nodes)

		popped = heap.popleft()
		assert not popped

	def test_heap_overload_doesnt_exceed_maxsize(self, mknode):
		maxsize = 3
		node = NodeHeap(mknode(key="0:0"), maxsize)
		assert not node

		for digit in range(10):
			node.push(mknode(key=f"0:{digit}", node_type=NodeType.Peer))

		assert len(node) == maxsize
		assert len(list(node)) == maxsize

	def test_heap_iters_over_nsmallest_via_distance(self, mknode):
		heap = NodeHeap(mknode(key="0:0", node_type=NodeType.Peer), 5)
		nodes = [mknode(key=f"0:{x}", node_type=NodeType.Peer) for x in range(10)]
		for node in nodes:
			heap.push(node)

		for index, node in enumerate(heap):
			assert index < 5

	def test_remove(self, mknode):
		maxsize = 5
		heap = NodeHeap(mknode(key="0:0", node_type=NodeType.Peer), maxsize)
		nodes = [mknode(key=f"0:{x}", node_type=NodeType.Peer) for x in range(10)]
		for node in nodes:
			heap.push(node)

		heap.remove([nodes[0], nodes[1]])
		assert len(list(heap)) == maxsize

		for index, node in enumerate(heap):
			# we removed to elements so offset index to account for it
			assert index < maxsize
