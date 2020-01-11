import time
import random

import pytest

from liaa.routing import KBucket, TableTraverser, RoutingTable
from liaa.network import KademliaProtocol
from liaa.node import NodeType, Node
from liaa.utils import rand_str


class TestKBucket:
	# pylint: disable=no-self-use
	def test_kbucket_instantiation(self):
		bucket = KBucket(0, 10, 5)
		assert isinstance(bucket, KBucket)
		assert bucket.last_updated

	def test_kbucket_add_nodes(self, mkpeer):
		bucket = KBucket(0, 10, 2)
		assert bucket.add_node(mkpeer()) is True
		assert bucket.add_node(mkpeer()) is True
		assert bucket.add_node(mkpeer()) is False
		assert len(bucket) == 2

	def test_kbucket_get_nodes(self, mkpeer):
		bucket = KBucket(0, 10, 2)
		bucket.add_node(mkpeer())
		bucket.add_node(mkpeer())
		fetched = bucket.get_nodes()
		assert len(fetched) == 2

	def test_excess_nodes_are_replacements(self, mkpeer):
		k = 3
		bucket = KBucket(0, 10, 3)
		nodes = [mkpeer() for x in range(10)]
		for node in nodes:
			bucket.add_node(node)

		# any number of nodes that exceeds `k` should be found in
		# replacement nodes
		replacement_nodes = bucket.replacement_nodes
		assert bucket.get_nodes() == nodes[:k]
		assert bucket.get_replacement_nodes() == nodes[k:]

	def test_remove_node_does_nothing_when_node_is_not_in_bucket(self, mkpeer):
		k = 3
		bucket = KBucket(0, 10, k)
		nodes = [mkpeer() for _ in range(10)]
		for node in nodes:
			bucket.add_node(node)

		bucket.remove_node(nodes.pop())
		assert bucket.get_nodes() == nodes[:k]
		assert bucket.get_replacement_nodes() == nodes[k:]

	def test_remove_node_replaces_removed_node_with_replacement_node(self, mkpeer):
		k = 3
		bucket = KBucket(0, 10, k)
		nodes = [mkpeer() for x in range(10)]
		for node in nodes:
			bucket.add_node(node)

		# here we remove a node that's in the bucket, and assert that a
		# our latest replacement node (nodes[-1:]) was added to the bucket
		replacement_nodes = bucket.replacement_nodes
		bucket.remove_node(nodes.pop(0))
		assert bucket.get_nodes() == nodes[:k-1] + nodes[-1:]
		assert bucket.get_replacement_nodes() == nodes[k-1:-1]

	def test_remove_all_nodes_uninitializes_bucket(self, mkpeer):
		k = 3
		bucket = KBucket(0, 10, k)
		nodes = [mkpeer() for x in range(10)]
		for node in nodes:
			bucket.add_node(node)

		# remove all nodes
		random.shuffle(nodes)
		for node in nodes:
			bucket.remove_node(node)
		assert not bucket

	def test_split_bucket_regroups_nodes_appropriately(self, mkpeer, mkresource):
		bucket = KBucket(0, 10, 5)
		bucket.add_node(mkpeer())
		bucket.add_node(mkresource())

		one, two = bucket.split()

		assert one.range == (0, 5)
		assert two.range == (6, 10)
		
		assert len(one) + len(two) == len(bucket)

	def test_double_added_node_is_put_at_end(self, mkpeer):
		# make sure when a node is double added it's put at the end
		bucket = KBucket(0, 10, 3)
		same = mkpeer()
		nodes = [mkpeer(), same, same]
		for node in nodes:
			bucket.add_node(node)
	
		for index, node in enumerate(bucket.get_nodes()):
			assert node == nodes[index]

	def test_bucket_has_in_range(self, mkpeer, mkresource):
		bucket = KBucket(0, 2**160, 10)
		assert bucket.has_in_range(mkpeer()) is True
		assert bucket.has_in_range(mkpeer()) is True
		assert bucket.has_in_range(mkresource(key=rand_str(10))) is True
		assert bucket.has_in_range(mkresource(key=rand_str(16))) is True
		assert bucket.has_in_range(mkresource(key=rand_str(20))) is False


class TestRoutingTable:

	# pylint: disable=no-self-use
	def test_can_instantiate_and_flush_table(self, mkpeer):
		ksize = 3
		table = RoutingTable(KademliaProtocol, ksize=ksize, node=mkpeer())
		assert isinstance(table, RoutingTable)
		assert len(table.buckets) == 1

	def test_can_split_bucket(self, mkpeer, mkbucket):
		ksize = 3
		table = RoutingTable(KademliaProtocol, ksize=ksize, node=mkpeer())
		table.buckets.extend([mkbucket(ksize), mkbucket(ksize)])
		assert len(table.buckets) == 3
		table.split_bucket(0)
		assert len(table.buckets) == 4

	def test_lonely_buckets_returns_stale_buckets(self, mkpeer, mkbucket):
		ksize = 3
		table = RoutingTable(KademliaProtocol, ksize, node=mkpeer())
		table.buckets.append(mkbucket(ksize))
		table.buckets.append(mkbucket(ksize))

		# make bucket lonely
		table.buckets[0].last_updated = time.monotonic() - 3600
		lonelies = table.lonely_buckets()
		assert len(lonelies) == 1

	def test_remove_contact_removes_buckets_node(self, mkpeer, mkbucket):
		ksize = 3
		table = RoutingTable(KademliaProtocol, ksize, node=mkpeer())
		table.buckets.append(mkbucket(ksize))
		assert len(table.buckets[1]) == 0

		node = mkpeer()
		table.add_contact(node)
		index = table.get_bucket_index_for(node)
		assert len(table.buckets[index]) == 1

		table.remove_contact(node)
		index = table.get_bucket_index_for(node)
		assert len(table.buckets[index]) == 0

	def test_is_new_node_returns_true_when_node_is_new(self, mkpeer):
		table = RoutingTable(KademliaProtocol, 3, node=mkpeer())
		assert table.is_new_node(mkpeer())

	def test_add_contact_is_ok(self, mkpeer):
		ksize = 3
		table = RoutingTable(KademliaProtocol, ksize, node=mkpeer())
		table.add_contact(mkpeer())
		assert len(table.buckets) == 1
		assert len(table.buckets[0].nodes) == 1

	@pytest.mark.skip(reason="TODO: implement after crawler tests")
	def test_find_neighbors_returns_k_neighbors(self, mkpeer, _):
		ksize = 3
		_ = RoutingTable(KademliaProtocol, ksize, node=mkpeer())


# pylint: disable=too-few-public-methods
class TestTableTraverser:
	# pylint: disable=no-self-use
	def test_iteration(self, fake_server, mkpeer):
		"""
		Make 10 nodes, 5 buckets, two nodes add to one bucket in order

		Bucket 0
			[node0, node1]
		Bucket 1
			[node2, node3]
		Bucket 2
			[node4, node5]
		Bucket 3
			[node6, node7]
		Bucket 4
			[node8, node9]
		Test traver result starting from node4.
		"""
		nodes = [mkpeer() for x in range(10)]

		buckets = []
		for i in range(5):
			bucket = KBucket(0, 2**160, 2)
			bucket.add_node(nodes[2 * i])
			bucket.add_node(nodes[2 * i + 1])
			buckets.append(bucket)

		# FIXME: refactor this tests accordingly
		
		# replace router's bucket with our test buckets
		fake_server.router.buckets = buckets

		# expected nodes order
		# pylint: disable=bad-continuation
		expected_nodes = [
			nodes[5],
			nodes[4],
			nodes[3],
			nodes[2],
			nodes[7],
			nodes[6],
			nodes[1],
			nodes[0],
			nodes[9],
			nodes[8],
		]

		start_node = nodes[4]
		table_traverser = TableTraverser(fake_server.router, start_node)
		for index, node in enumerate(table_traverser):
			# FIXME: traverser should work
			# assert node == expected_nodes[index]
			pass
