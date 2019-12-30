import random
import hashlib
from collections.abc import Iterable

from kademlia.node import Node, NodeHeap
from kademlia.utils import hex_to_int


class TestNode:
	# pylint: disable=no-self-use
	def test_node_long_id_derivation_is_ok(self):
		rid = hashlib.sha1(str(random.getrandbits(255)).encode()).digest()
		node = Node(rid)
		assert node.long_id == hex_to_int(rid.hex())

	def test_valid_diff_calculation_is_ok(self):
		ridone = hashlib.sha1(str(random.getrandbits(255)).encode())
		ridtwo = hashlib.sha1(str(random.getrandbits(255)).encode())

		shouldbe = hex_to_int(ridone.digest().hex()) ^ hex_to_int(ridtwo.digest().hex())
		none = Node(ridone.digest())
		ntwo = Node(ridtwo.digest())
		assert none.distance_to(ntwo) == shouldbe

	def test_distance_diff_of_same_node_is_0(self, mknode):
		node_one = mknode(intid=1)
		node_two = mknode(intid=1)
		assert node_one.distance_to(node_two) == 0

	def test_is_same_node(self, mknode):
		node_one = mknode(ip_addy="0.0.0.0", port=0000)
		node_two = mknode(ip_addy="0.0.0.0", port=0000)
		assert node_one.is_same_node(node_two)

	def test_node_iter(self, mknode):
		node = mknode()
		assert tuple(node) == (node.digest_id, node.ip, node.port)


class TestNodeHeap:
	# pylint: disable=no-self-use
	def test_can_create_nodeheap(self, mknode):
		heap = NodeHeap(mknode(), 2)
		assert isinstance(heap, NodeHeap)

	def test_get_node_return_node_when_node_present(self, mknode):
		heap = NodeHeap(mknode(), 3)
		nodes = [mknode(intid=i) for i in range(3)]
		# pylint: disable=invalid-name
		for n in nodes:
			heap.push(n)
		node = heap.get_node(nodes[0].digest_id)
		assert isinstance(node, Node)

	def test_get_node_returns_none_when_node_not_exists(self, mknode):
		heap = NodeHeap(mknode(), 1)
		empty = heap.get_node(123)
		assert not empty

	def test_mark_contacted_works_ok(self, mknode):
		maxsize = 10
		heap = NodeHeap(mknode(), maxsize)
		nodes = [mknode(intid=i) for i in range(maxsize)]
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
		heap = NodeHeap(mknode(), maxsize)
		nodes = [mknode(intid=i) for i in range(maxsize)]
		for node in nodes:
			heap.push(node)

		popped = heap.popleft()
		assert isinstance(popped, Node)

	def test_popleft_returns_none_when_heap_empty(self, mknode):
		maxsize = 1
		heap = NodeHeap(mknode(), maxsize)
		nodes = [mknode(intid=i) for i in range(maxsize)]
		for node in nodes:
			heap.push(node)

		heap.remove(nodes)
		popped = heap.popleft()
		assert isinstance(popped, Iterable)
		# pylint: disable=invalid-name
		_, ip, port = tuple(popped)
		assert (not ip) and (not port)


	def test_heap_overload_doesnt_exceed_maxsize(self, mknode):
		maxsize = 3
		node = NodeHeap(mknode(intid=0), maxsize)
		assert not node

		for digit in range(10):
			node.push(mknode(intid=digit))

		assert len(node) == maxsize
		assert len(list(node)) == maxsize

	def test_heap_iters_over_nsmallest_via_distance(self, mknode):
		heap = NodeHeap(mknode(intid=0), 5)
		nodes = [mknode(intid=x) for x in range(10)]
		for index, node in enumerate(nodes):
			heap.push(node)

		for index, node in enumerate(heap):
			assert index == node.long_id
			assert index < 5

	def test_remove(self, mknode):
		maxsize = 5
		heap = NodeHeap(mknode(intid=0), maxsize)
		nodes = [mknode(intid=x) for x in range(10)]
		for node in nodes:
			heap.push(node)

		heap.remove([nodes[0].digest_id, nodes[1].digest_id])
		# len(heap) == min(10-2, maxsize)
		assert len(list(heap)) == maxsize

		for index, node in enumerate(heap):
			# we removed to elements so offset index to account for it
			assert index + 2 == node.long_id
			assert index < maxsize
