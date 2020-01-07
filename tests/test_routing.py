import time
import random

import pytest

from liaa.routing import KBucket, TableTraverser, RoutingTable
from liaa.network import KademliaProtocol

class TestKBucket:
	# pylint: disable=no-self-use
	def test_can_create_bucket(self):
		bucket = KBucket(0, 10, 5)
		assert isinstance(bucket, KBucket)
		assert bucket.last_updated

	def test_can_add_nodes_to_bucket(self, mknode):
		bucket = KBucket(0, 10, 2)
		assert bucket.add_node(mknode()) is True
		assert bucket.add_node(mknode()) is True
		assert bucket.add_node(mknode()) is False
		assert len(bucket) == 2

	def test_get_nodes_returns_proper_nodes(self, mknode):
		bucket = KBucket(0, 10, 2)
		bucket.add_node(mknode(intid=1))
		bucket.add_node(mknode(intid=2))
		fetched = bucket.get_nodes()
		assert len(fetched) == 2

	def test_replacement_nodes_are_excess_pushed_nodes(self, mknode):
		k = 3
		bucket = KBucket(0, 10, k)
		nodes = [mknode() for _ in range(10)]
		for node in nodes:
			bucket.add_node(node)

		# any number of nodes that exceeds `k` should be found in
		# replacement nodes
		replacement_nodes = bucket.replacement_nodes
		assert list(bucket.nodes.values()) == nodes[:k]
		assert list(replacement_nodes.values()) == nodes[k:]

	def test_remove_node_does_nothing_when_node_is_not_in_bucket(self, mknode):
		k = 3
		bucket = KBucket(0, 10, k)
		nodes = [mknode() for _ in range(10)]
		for node in nodes:
			bucket.add_node(node)

		# we remove a node that's not in the bucket (a replacement node) so
		# nothing should change
		replacement_nodes = bucket.replacement_nodes
		bucket.remove_node(nodes.pop())
		assert list(bucket.nodes.values()) == nodes[:k]
		assert list(replacement_nodes.values()) == nodes[k:]

	def test_remove_node_replaces_removed_node_with_replacement_node(self, mknode):
		k = 3
		bucket = KBucket(0, 10, k)
		nodes = [mknode() for _ in range(10)]
		for node in nodes:
			bucket.add_node(node)

		# here we remove a node that's in the bucket, and assert that a
		# our latest replacement node (nodes[-1:]) was added to the bucket
		replacement_nodes = bucket.replacement_nodes
		bucket.remove_node(nodes.pop(0))
		assert list(bucket.nodes.values()) == nodes[:k-1] + nodes[-1:]
		assert list(replacement_nodes.values()) == nodes[k-1:-1]

	def test_remove_all_nodes_uninitializes_bucket(self, mknode):
		k = 3
		bucket = KBucket(0, 10, k)
		nodes = [mknode() for _ in range(10)]
		for node in nodes:
			bucket.add_node(node)

		replacement_nodes = bucket.replacement_nodes

		# remove all nodes
		random.shuffle(nodes)
		for node in nodes:
			bucket.remove_node(node)
		assert not bucket
		assert not replacement_nodes

	def test_split_bucket_regroups_nodes_appropriately(self, mknode):
		bucket = KBucket(0, 10, 5)
		bucket.add_node(mknode(intid=5))
		bucket.add_node(mknode(intid=6))

		one, two = bucket.split()
		assert len(one) == 1
		assert one.range == (0, 5)
		assert len(two) == 1
		assert two.range == (6, 10)

	def test_double_node_is_put_at_end_when_added_twice(self, mknode):
		# make sure when a node is double added it's put at the end
		bucket = KBucket(0, 10, 3)
		nodes = [mknode(), mknode(), mknode()]
		for node in nodes:
			bucket.add_node(node)
		for index, node in enumerate(bucket.get_nodes()):
			assert node == nodes[index]

	def test_has_in_range_works_ok(self, mknode):
		bucket = KBucket(0, 10, 10)
		assert bucket.has_in_range(mknode(intid=5)) is True
		assert bucket.has_in_range(mknode(intid=11)) is False
		assert bucket.has_in_range(mknode(intid=10)) is True
		assert bucket.has_in_range(mknode(intid=0)) is True


class TestRoutingTable:

	# pylint: disable=no-self-use
	def test_can_instantiate_and_flush_table(self, mknode):
		ksize = 3
		table = RoutingTable(KademliaProtocol, ksize=ksize, node=mknode())
		assert isinstance(table, RoutingTable)
		assert len(table.buckets) == 1

	def test_can_split_bucket(self, mknode, mkbucket):
		ksize = 3
		table = RoutingTable(KademliaProtocol, ksize=ksize, node=mknode())
		table.buckets.extend([mkbucket(ksize), mkbucket(ksize)])
		assert len(table.buckets) == 3
		table.split_bucket(0)
		assert len(table.buckets) == 4

	def test_lonely_buckets_returns_stale_buckets(self, mknode, mkbucket):
		ksize = 3
		table = RoutingTable(KademliaProtocol, ksize, node=mknode())
		table.buckets.append(mkbucket(ksize))
		table.buckets.append(mkbucket(ksize))

		# make bucket lonely
		table.buckets[0].last_updated = time.monotonic() - 3600
		lonelies = table.lonely_buckets()
		assert len(lonelies) == 1

	def test_remove_contact_removes_buckets_node(self, mknode, mkbucket):
		ksize = 3
		table = RoutingTable(KademliaProtocol, ksize, node=mknode())
		table.buckets.append(mkbucket(ksize))
		assert len(table.buckets[1]) == 0

		node = mknode()
		table.add_contact(node)
		index = table.get_bucket_index_for(node)
		assert len(table.buckets[index]) == 1

		table.remove_contact(node)
		index = table.get_bucket_index_for(node)
		assert len(table.buckets[index]) == 0

	def test_is_new_node_returns_true_when_node_is_new(self, mknode):
		table = RoutingTable(KademliaProtocol, 3, node=mknode())
		assert table.is_new_node(mknode())

	def test_add_contact_is_ok(self, mknode):
		ksize = 3
		table = RoutingTable(KademliaProtocol, ksize, node=mknode())
		table.add_contact(mknode())
		assert len(table.buckets) == 1
		assert len(table.buckets[0].nodes) == 1

	@pytest.mark.skip(reason="TODO: implement after crawler tests")
	def test_find_neighbors_returns_k_neighbors(self, mknode, _):
		ksize = 3
		_ = RoutingTable(KademliaProtocol, ksize, node=mknode())


# pylint: disable=too-few-public-methods
class TestTableTraverser:
	# pylint: disable=no-self-use
	def test_iteration(self, fake_server, mknode):
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

		nodes = [mknode(intid=x) for x in range(10)]

		buckets = []
		for i in range(5):
			bucket = KBucket(2 * i, 2 * i + 1, 2)
			bucket.add_node(nodes[2 * i])
			bucket.add_node(nodes[2 * i + 1])
			buckets.append(bucket)

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
			assert node == expected_nodes[index]
