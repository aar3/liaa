import os
import sys
import json
import pytest
from liaa import *


TEST_WITH_SOCKETS = os.environ.get("TEST_WITH_SOCKETS")


class TestUtils:
    def test_bytes_to_bits_returns_proper_bit_string(self):
        pass

class TestBaseNode:
    def test_create_node_sets_initialized_props(self):
        node = BaseNode(key="foo")
        assert isinstance(node.long_id, int)

    def test_distance_to_returns_distance_from_long_ids(self):
        node1 = BaseNode(key="foo")
        node2 = BaseNode(key="bar")
        distance = node1.distance_to(node2)

        assert isinstance(distance, int)
        assert distance > 0


class TestPeerNode:
    @pytest.mark.skip(reason="Not implemented")
    def test_set_payload_sets_property_on_node(self):
        pass

    def test_serialize_returns_serialized_properties(self):
        node = PeerNode(key="0.0.0.0:0000")
        node.set_payload("payload")
        dump = node.serialize()

        expected = json.dumps({"key":node.key, "long_id":node.long_id, "value":node.payload})

        assert expected == node.serialize()


class TestCacheNode:
    def test_set_payload_sets_property_on_node(self):
        node = CacheNode(key="foo")
        node.set_payload({"key": b"value"})

        assert node.payload == {"key": b"value"}

    def test_serialize_returns_serialized_properties(self):
        node = CacheNode(key="foo")
        node.set_payload({"key": b"value"})

        expected = json.dumps({"key":node.key, "long_id":node.long_id, "value":"value"})

        assert expected == node.serialize()


class TestKbucket:
    def test_pushing_to_bucket_goes_to_main_set_first(self, generic_node):
        k = KBucket(0, 2**10, 3)
       
        for _ in range(3):
            k.add_node(generic_node())

        assert len(k) == 3

    def test_additions_exceeding_ksize_goes_to_replacement_nodes(self, generic_node):
        k = KBucket(0, 2**10, 3)
        
        for _ in range(5):
            k.add_node(generic_node())

        assert len(k) == 3
        assert len(k.replacement_set) == 2

    def test_removal_of_node_adds_replacement_node_to_main_set(self, generic_node, kbucket):
        k = kbucket()
        nodes = []
        for _ in range(5):
            n = generic_node()
            k.add_node(n)
            nodes.append(n)

        to_remove = nodes[1]

        assert len(k.main_set) == 3
        assert len(k.replacement_set) == 2

        k.remove_node(to_remove)

        assert len(k.main_set) == 3
        assert len(k.replacement_set) == 1

        assert to_remove not in k.main_set

    def test_has_in_range_returns_True_when_bucket_has_node_in_range(self, generic_node, kbucket):
        bucket = kbucket()
        node = generic_node()
        return bucket.has_in_range(node)



class TestRoutingTable:
    def test_creation_flushes_buckets(self, routing_table):
        table = routing_table()
        assert len(table.buckets) == 1

    def test_splits_bucket_adds_new_bucket(self, routing_table):
        table = routing_table()
        table.split_bucket(0)

        assert len(table.buckets) == 2
        assert table.buckets[0].range[1] <= table.buckets[1].range[0]

    def test_lonely_buckets_returns_buckets_with_no_updated_in_past_hour(self, routing_table, generic_node):

        table = routing_table()

        for i in range(5):
            table.add_node(generic_node())
                
        assert len(table.buckets) == 3
        
        table.buckets[0].last_seen = -3700

        lonely = table.lonely_buckets()

        assert len(lonely) == 1

    def test_add_node_properly_implements_bucket_split_functionality(self, routing_table, generic_node):
        table = routing_table()
        nodes = [generic_node() for _ in range(5)]
    
        assert len(table.buckets) == 1

        for n in nodes:
            table.add_node(n)


    
    @pytest.mark.skip(reason="Not finished")
    def test_remove_node_makes_bucket_remove_node(self, routing_table, generic_node):
        table = routing_table()
        nodes = [generic_node() for _ in range(3)]
        for n in nodes:
            table.add_node(n)

        assert table.count_of_nodes_in_table() == 2.

        bucket = table.get_bucket_index(0)
        assert nodes[0] in bucket.main_set

        table.remove_node(nodes[0])

        assert nodes[0] not in bucket.main_set


class TestNodeHeap:
    def test_can_create_node_heap(self, node_heap, generic_node):
        heap = node_heap()
        assert len(heap.heap) == 0
        assert heap.has_exhausted_contacts()

    def test_heap_orders_by_distance(self, node_heap, generic_node):
        heap = node_heap()

        for _ in range(2):
            nodes = [generic_node() for _ in range(2)]
            heap.push(nodes)

        
