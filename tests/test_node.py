import random
import hashlib
from collections.abc import Iterable

from liaa.node import Node, NodeHeap, PeerNode, ResourceNode
from liaa.utils import hex_to_int, pack


class TestNode:
	# pylint: disable=no-self-use
	def test_peer_node(self):
		node = PeerNode(key='127.0.0.1:8080')
		assert isinstance(node, PeerNode)
		assert node.ip == "127.0.0.1"
		assert node.port == 8080
		assert node.node_type == 'peer'
		assert not node.value
		assert node.digest == pack("I", node.key)
		assert node.long_id < 2**160
		assert str(node) == "peer@127.0.0.1:8080"

	def test_resource_node(self):
		node = ResourceNode(key='my-node', value=b'123')
		assert isinstance(node, ResourceNode)
		assert node.node_type == 'resource'
		assert node.digest == pack("I", node.key)
		assert node.long_id < 2**160
		assert str(node) == 'resource@my-node'

	def test_distance_calculation(self, mkpeer):

		addr1 = "127.0.0.1:8000"
		addr2 = "127.0.0.1:9000"

		none = mkpeer(key=addr1)
		ntwo = mkpeer(key=addr2)

		shouldbe = hex_to_int(pack("I", addr1).hex()) ^ hex_to_int(pack("I", addr2).hex())

		assert none.distance_to(ntwo) == shouldbe

	def test_node_is_same_node(self, mkpeer):
		node_one = node_two = mkpeer()
		assert node_one.distance_to(node_two) == 0
		assert node_one.is_same_node(node_two)

	def test_node_iter(self, mkpeer):
		node = mkpeer()
		assert tuple(node) == (node.digest, node.ip, node.port)


class TestNodeHeap:
	# pylint: disable=no-self-use
	def test_can_create_nodeheap(self, mkpeer):
		heap = NodeHeap(mkpeer(), 2)
		assert isinstance(heap, NodeHeap)

	def test_get_node_return_node_when_node_present(self, mkpeer):
		heap = NodeHeap(mkpeer(), 3)
		nodes = [mkpeer() for _ in range(3)]
		for node in nodes:
			heap.push(node)
		node = heap.get_node(nodes[0].digest)
		assert isinstance(node, Node)

	def test_get_node_returns_none_when_node_not_exists(self, mkpeer):
		heap = NodeHeap(mkpeer(), 1)
		empty = heap.get_node(123)
		assert not empty

	def test_mark_contacted_works_ok(self, mkpeer):
		maxsize = 10
		heap = NodeHeap(mkpeer(), maxsize)
		nodes = [mkpeer() for _ in range(maxsize)]
		for node in nodes:
			heap.push(node)
		contacted = nodes[:5]
		for node in contacted:
			heap.mark_contacted(node)

		assert len(heap.contacted) == 5
		assert not heap.have_contacted_all()
		assert len(heap.get_uncontacted()) == 5

	def test_popleft_returns_left_if_heap_not_empty(self, mkpeer):
		maxsize = 5
		heap = NodeHeap(mkpeer(), maxsize)
		nodes = [mkpeer() for _ in range(maxsize)]
		for node in nodes:
			heap.push(node)

		popped = heap.popleft()
		assert isinstance(popped, Node)

	def test_popleft_returns_none_when_heap_empty(self, mkpeer):
		maxsize = 1
		heap = NodeHeap(mkpeer(), maxsize)
		nodes = [mkpeer()]
		for node in nodes:
			heap.push(node)

		heap.remove(nodes)

		popped = heap.popleft()
		assert not popped

	def test_heap_overload_doesnt_exceed_maxsize(self, mkpeer):
		maxsize = 3
		node = NodeHeap(mkpeer(), maxsize)
		assert not node

		for digit in range(10):
			node.push(mkpeer())

		assert len(node) == maxsize
		assert len(list(node)) == maxsize

	def test_heap_iters_over_nsmallest_via_distance(self, mkpeer):
		heap = NodeHeap(mkpeer(), 5)
		nodes = [mkpeer() for _ in range(10)]
		for node in nodes:
			heap.push(node)

		for index, node in enumerate(heap):
			assert index < 5

	def test_remove(self, mkpeer):
		maxsize = 5
		heap = NodeHeap(mkpeer(), maxsize)
		nodes = [mkpeer() for _ in range(10)]
		for node in nodes:
			heap.push(node)

		heap.remove([nodes[0], nodes[1]])
		assert len(list(heap)) == maxsize

		for index, node in enumerate(heap):
			# we removed to elements so offset index to account for it
			assert index < maxsize
