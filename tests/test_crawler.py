import pytest

from liaa.crawler import SpiderCrawl
from liaa.protocol import KademliaProtocol
from liaa.node import NodeHeap


# pylint: disable=too-few-public-methods
class FakeSpiderCrawler:
    def __init__(self, protocol, node, peers, ksize, alpha):
        self.protocol = protocol
        self.node = node
        self.peers = peers
        self.ksize = ksize
        self.alpha = alpha


def fake_spider_crawler(node):
    return SpiderCrawl(KademliaProtocol, node=node, peers=[], ksize=3, alpha=3)


class TestSpiderCrawl:
    # pylint: disable=no-self-use
    def test_can_init_crawler(self, make_network_node):
        crawler = fake_spider_crawler(node=make_network_node())
        assert isinstance(crawler, SpiderCrawl)
        assert isinstance(crawler.nearest, NodeHeap)
        assert not crawler.nearest

    @pytest.mark.skip(reason="not implemented")
    def test_find_returns_expected_result(self, make_basic_node):
        crawler = fake_spider_crawler(node=make_basic_node())
        assert not crawler.last_ids_crawled
        crawler.nearest.push([make_basic_node(intid=i) for i in range(5)])
