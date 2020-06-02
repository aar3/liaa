# pylint: disable=line-too-long

import asyncio

import pytest

from liaa.crawler import SpiderCrawl
from liaa.protocol import KademliaProtocol
from liaa.node import NodeHeap, PingNode, IndexNode


class TestSpiderCrawl:
    def test_can_init_crawler(self, fake_spider_crawler):
        crawler = fake_spider_crawler()
        assert isinstance(crawler, SpiderCrawl)
        assert isinstance(crawler.nearest, NodeHeap)
        assert not crawler.nearest
        assert not crawler.last_ids_crawled
        assert not crawler.nearest.get_uncontacted()
        assert not crawler.nearest

    @pytest.mark.asyncio
    async def test_find_marks_given_ping_nodes_as_last_nodes_seen(
        self, fake_spider_crawler, generic_node, sandbox
    ):
        nodes = [generic_node() for _ in range(5)]
        crawler = fake_spider_crawler(peers=nodes)

        async def fake_rpcmethod(*args):
            await asyncio.sleep(1)

        async def parse_response_results_stub(nodes):
            await asyncio.sleep(1)
            return nodes

        box = sandbox(crawler)
        box.stub("_parse_response_results", parse_response_results_stub)

        # pylint: disable=protected-access
        _ = await crawler._find(fake_rpcmethod)
        assert crawler.last_ids_crawled == crawler.nearest.get_ids()

    @pytest.mark.asyncio
    async def test_find_only_marks_ping_nodes_as_contacted(
        self, fake_spider_crawler, generic_node, sandbox
    ):
        nodes = [generic_node() for _ in range(5)]
        crawler = fake_spider_crawler(peers=nodes)

        async def fake_rpcmethod(*args):
            await asyncio.sleep(1)

        async def parse_response_results_stub(nodes):
            await asyncio.sleep(1)
            return nodes

        box = sandbox(crawler)
        box.stub("_parse_response_results", parse_response_results_stub)

        # pylint: disable=protected-access
        _ = await crawler._find(fake_rpcmethod)
        assert all([isinstance(n, PingNode) for n in crawler.nearest.get_concatcted()])


class TestNodeSpiderCrawl:
    @pytest.mark.skip(
        reason="this is mostly handled by SpiderCrawl.test_find_only_marks_ping_nodes_as_contacted"
    )
    def test_find_calls_rpcmethod_on_uncontacted_ping_nodes_and_marks_contacted(self):
        pass

    @pytest.mark.asyncio
    async def test_nodes_found_prunes_neighbors_and_makes_recursive_calls(
        self, fake_node_crawler, sandbox, generic_node
    ):

        nodes = [generic_node() for _ in range(10)]
        crawler = fake_node_crawler(peers=nodes)

        assert crawler.nearest.true_size() == len(nodes)

        async def find_stub(*args):
            await asyncio.sleep(1)

        box = sandbox(crawler)
        box.stub("find", find_stub)

        responses = {
            nodes[0].key: (True, ["0.0.0:100", "0.0.1", 100]),
            nodes[1].key: (True, ["0.0.0:000", "0.0.0", 000]),
            nodes[2].key: (False,),
            nodes[3].key: (True,),
        }

        # pylint: disable=protected-access
        _ = await crawler._parse_response_results(responses)

        assert crawler.nearest.true_size() == len(nodes)
        assert not crawler.nearest.has_exhausted_contacts()


class TestValueSpiderCrawl:
    @pytest.mark.skip(
        reason="this is mostly handled by SpiderCrawl.test_find_only_marks_ping_nodes_as_contacted"
    )
    async def test_find_calls_rpcmethod_on_uncontacted_ping_nodes_and_marks_contacted(
        self,
    ):
        pass

    async def test_nodes_found_prunes_neighbors_and_handles_found_values(
        self, generic_node, fake_value_crawler, sandbox
    ):
        nodes = [generic_node() for _ in range(10)]
        crawler = fake_value_crawler(peers=nodes)

        async def find_stub(*args):
            await asyncio.sleep(1)

        box = sandbox(crawler)
        box.stub("find", find_stub)

        responses = {
            nodes[0].key: (True, {"foo": b"bar"}),
            nodes[1].key: (True, {"zoo": b"foo"}),
            nodes[2].key: (False,),
            nodes[3].key: (True,),
        }

        # pylint: disable=protected-access
        _ = await crawler._parse_response_results(responses)

        assert crawler.nearest.has_exhausted_contacts()

    @pytest.mark.skip(reason="TODO")
    async def test_handle_found_values_asks_nearest_peer_without_value_to_store_index_node_data(
        self,
    ):
        pass
