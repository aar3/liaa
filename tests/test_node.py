import random
import hashlib


from kademlia.node import Node, NodeHeap
from kademlia.utils import hex_to_base_int


class TestNode:
	def test_long_id(self):  # pylint: disable=no-self-use
		rid = hashlib.sha1(str(random.getrandbits(255)).encode()).digest()
		node = Node(rid)
		assert node.long_id == hex_to_base_int(rid.hex())

	def test_distance_calculation(self):  # pylint: disable=no-self-use
		ridone = hashlib.sha1(str(random.getrandbits(255)).encode())
		ridtwo = hashlib.sha1(str(random.getrandbits(255)).encode())

		shouldbe = hex_to_base_int(ridone.digest().hex()) ^ hex_to_base_int(ridtwo.digest().hex())
		none = Node(ridone.digest())
		ntwo = Node(ridtwo.digest())
		assert none.distance_to(ntwo) == shouldbe


class TestNodeHeap:
	"""
	For test_max_size and test_iteration:

	NodeHeap will always have len <= NodeHeap.max_size, and
	NodeHeap.__iter__ will only return `n` nodes that have asmallest
	distance from NodeHeap.node, where `n` <= NodeHeap.max_size
	"""

	def test_max_size(self, mknode):  # pylint: disable=no-self-use
		node = NodeHeap(mknode(intid=0), 3)
		assert not node

		for digit in range(10):
			node.push(mknode(intid=digit))

		assert len(node) == 3
		assert len(list(node)) == 3

	def test_iteration(self, mknode):  # pylint: disable=no-self-use
		heap = NodeHeap(mknode(intid=0), 5)
		nodes = [mknode(intid=x) for x in range(10)]
		for index, node in enumerate(nodes):
			heap.push(node)

		for index, node in enumerate(heap):
			assert index == node.long_id
			assert index < 5

	def test_remove(self, mknode):  # pylint: disable=no-self-use
		heap = NodeHeap(mknode(intid=0), 5)
		nodes = [mknode(intid=x) for x in range(10)]
		for node in nodes:
			heap.push(node)

		heap.remove([nodes[0].id, nodes[1].id])
		assert len(list(heap)) == 5
		for index, node in enumerate(heap):
			# we removed to elements so offset index to account for it
			assert index + 2 == node.long_id
			assert index < 5
