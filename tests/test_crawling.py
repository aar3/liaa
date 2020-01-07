import pytest

from liaa.crawling import SpiderCrawl
from liaa.network import KademliaProtocol
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
	def test_can_init_crawler(self, mknode):
		crawler = fake_spider_crawler(node=mknode())
		assert isinstance(crawler, SpiderCrawl)
		assert isinstance(crawler.nearest, NodeHeap)
		assert len(crawler.nearest) == 0

	@pytest.mark.skip(reason="not implemented")
	def test_find_returns_expected_result(self, mknode):
		crawler = fake_spider_crawler(node=mknode())
		assert len(crawler.last_ids_crawled) == 0
		crawler.nearest.push([mknode(intid=i) for i in range(5)])
