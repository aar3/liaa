import time
import random

import pytest

from liaa import MAX_LONG
from liaa.routing import KBucket, TableTraverser, RoutingTable, LRU
from liaa.server import KademliaProtocol
from liaa.utils import rand_str, join_addr



class TestLRU:
	# pylint: disable=no-self-use
	def test_can_init_lru(self):
		lru = LRU(maxsize=10)
		assert isinstance(lru, LRU)
		assert lru.maxsize == 10

	def test_can_add_item_to_lru(self):
		lru = LRU(maxsize=10)
		items = [(x, str(x)) for x in range(5)]
		for key, val in items:
			lru.add(key, val)
		assert len(lru) == 5

	def test_can_add_to_lru_head(self, mklru):
		lru = mklru()
		lru.add_head(-1, "-1")
		assert len(lru) == 6

		item = lru.items()[0]

		assert item == (-1, "-1")

	def test_can_pop_from_lru(self, mklru):
		lru = mklru()
		lru.add(11, 11)
		assert lru.pop() == (11, 11)


class TestKBucket:
	# pylint: disable=no-self-use
	def test_can_init_bucket(self):
		bucket = KBucket(0, 10, 5)
		assert isinstance(bucket, KBucket)
		assert bucket.last_seen

	def test_can_add_node_to_bucket(self, mkpeer):
		bucket = KBucket(0, 10, 2)
		assert bucket.add_node(mkpeer()) is True
		assert bucket.add_node(mkpeer()) is True
		assert bucket.add_node(mkpeer()) is False
		assert len(bucket) == 2

	def test_can_get_node_from_bucket(self, mkpeer):
		bucket = KBucket(0, 10, 2)
		bucket.add_node(mkpeer())
		bucket.add_node(mkpeer())
		fetched = bucket.get_set()
		assert len(fetched) == 2

	def test_excess_nodes_added_to_bucket_become_replacements(self, mkpeer):
		k = 3
		bucket = KBucket(0, 10, 3)
		nodes = [mkpeer() for x in range(10)]
		for node in nodes:
			bucket.add_node(node)

		assert bucket.get_set() == nodes[:k]
		assert bucket.get_replacement_set() == nodes[k:]

	def test_remove_replaces_with_replacement(self, mknode):
		bucket = KBucket(0, 10, 3)
		nodes = [mknode() for x in range(10)]
		for node in nodes:
			bucket.add_node(node)
		assert len(bucket.replacement_set) == 7

		replacements = bucket.get_replacement_set()
		bucket.remove_node(nodes.pop(0))
		assert len(bucket.get_replacement_set()) == 6
		assert replacements[-1] in bucket.get_set()

	def test_remove_all_nodes_uninitializes_bucket(self, mknode):
		bucket = KBucket(0, 10, 3)
		nodes = [mknode() for x in range(10)]
		for node in nodes:
			bucket.add_node(node)


		random.shuffle(nodes)
		for node in nodes:
			bucket.remove_node(node)
		assert not bucket

	def test_can_split(self, mkpeer, mkresource):
		bucket = KBucket(0, 10, 5)
		bucket.add_node(mkpeer())
		bucket.add_node(mkresource())

		one, two = bucket.split()

		assert one.range == (0, 5)
		assert two.range == (6, 10)

		assert len(one) + len(two) == len(bucket)

	def test_double_added_node_is_put_at_end(self, mkpeer):
		# make sure when a node is double added it"s put at the end
		bucket = KBucket(0, 10, 3)
		same = mkpeer()
		nodes = [mkpeer(), same, same]
		for node in nodes:
			bucket.add_node(node)

		for index, node in enumerate(bucket.get_set()):
			assert node == nodes[index]

	def test_bucket_has_in_range(self, mkpeer, mkresource):
		bucket = KBucket(0, MAX_LONG, 10)
		assert bucket.has_in_range(mkpeer()) is True
		assert bucket.has_in_range(mkpeer()) is True
		assert bucket.has_in_range(mkresource(key=rand_str(10))) is True
		assert bucket.has_in_range(mkresource(key=rand_str(16))) is True
		assert bucket.has_in_range(mkresource(key=rand_str(19))) is True

		try:
			bucket.has_in_range(mkresource(key=rand_str(21))) is False
		except OverflowError as err:
			assert str(err).endswith("cannot exceed " + str(MAX_LONG))


class TestRoutingTable:

	# pylint: disable=no-self-use
	def test_can_flush_table(self, mkpeer):
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

	def test_lonely_buckets_returns_stale(self, mkpeer, mkbucket, mknode):
		ksize = 3
		table = RoutingTable(KademliaProtocol, ksize, node=mkpeer())
		table.buckets.append(mkbucket(ksize))
		table.buckets[0].add_node(mknode())
		table.buckets.append(mkbucket(ksize))

		# make bucket lonely
		table.buckets[0].last_seen = time.monotonic() - 3600
		lonelies = table.lonely_buckets()
		assert len(lonelies) == 1

	def test_remove_contact_removes_buckets_node(self, mkpeer, mkbucket):
		ksize = 3
		table = RoutingTable(KademliaProtocol, ksize, node=mkpeer())
		table.buckets.append(mkbucket(ksize))
		assert not table.buckets[1]

		node = mkpeer()
		table.add_contact(node)
		index = table.get_bucket_index_for(node)
		assert len(table.buckets[index]) == 1

		table.remove_contact(node)
		index = table.get_bucket_index_for(node)
		assert not table.buckets[index]

	def test_is_new_node(self, mkpeer):
		table = RoutingTable(KademliaProtocol, 3, node=mkpeer())
		assert table.is_new_node(mkpeer())

	def test_add_contact(self, mkpeer):
		ksize = 3
		table = RoutingTable(KademliaProtocol, ksize, node=mkpeer())
		table.add_contact(mkpeer())
		assert len(table.buckets) == 1
		assert len(table.buckets[0]) == 1

	@pytest.mark.skip(reason="TODO: implement after crawler tests")
	def test_find_neighbors_returns_k_neighbors(self, mkpeer, _):
		ksize = 3
		_ = RoutingTable(KademliaProtocol, ksize, node=mkpeer())


# pylint: disable=too-few-public-methods
class TestTableTraverser:
	# pylint: disable=no-self-use
	def test_iteration(self, fake_server, mkpeer):
		nodes = []
		for port in range(8000, 8010):
			key = join_addr(("0.0.0.0", port))
			nodes.append(mkpeer(key))

		buckets = []
		for i in range(5):
			bucket = KBucket(0, MAX_LONG, 2)
			bucket.add_node(nodes[2 * i])
			bucket.add_node(nodes[2 * i + 1])
			buckets.append(bucket)

		fake_server.router.buckets = buckets

		# pylint: disable=bad-continuation
		expected_nodes = [
			nodes[1],
			nodes[0],
			nodes[3],
			nodes[2],
			nodes[5],
			nodes[4],
			nodes[7],
			nodes[6],
			nodes[9],
			nodes[8],
		]

		start_node = nodes[4]
		table_traverser = TableTraverser(fake_server.router, start_node)
		for index, node in enumerate(table_traverser):
			assert node == expected_nodes[index]
