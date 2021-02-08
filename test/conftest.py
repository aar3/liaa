import random
import pytest
from liaa import *

def random_node():
    key = random_string()
    return PeerNode(key=key) if random.randint(1, 10e10) % 2 else CacheNode(key=key)


@pytest.fixture
def generic_node():
    def _generic_node():
        return random_node()
    return _generic_node



@pytest.fixture
def kbucket():
    def _kbucket():
        return KBucket(0, MAX_LONG, 3)
    return _kbucket


@pytest.fixture
def routing_table(max_long=10):
    def _routing_table():
        key = random_string()
        return RoutingTable(None, KSIZE, PeerNode(key=key), max_long=max_long)
    return _routing_table

@pytest.fixture
def node_heap(source_node=None, max_size=3):
    def _node_heap():
        node = source_node or random_node()
        return NodeHeap(node, max_size)
    return _node_heap
