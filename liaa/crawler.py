import logging
import collections

from _typing import *

from liaa.utils import gather_dict
from liaa.node import NodeHeap, GenericNode, PingNode, IndexNode
from liaa.protocol import RPCFindResponse, KademliaProtocol


log = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class SpiderCrawl:
    def __init__(
        self,
        protocol: KademliaProtocol,
        node: GenericNode,
        peers: List[GenericNode],
        ksize: int,
        alpha: int,
    ):
        """
		The C{SpiderCrawl}er is a base class that is responsible for bootstrapping
		various sub-classes (sub-crawlers) with a list of necessary functions,
		including _find and _nodes_found methods

		Parameters
		-----------
			protocol: KademliaProtocol
				A (kademlia) protocol instance.
			node: GenericNode
				representing the key we're looking for
			peers: List[GenericNode]
				A list of instances that provide the entry point for the network
			ksize: int
				The value for k based on the paper
			alpha: int
				The value for alpha based on the paper
		"""
        self.protocol = protocol
        self.ksize = ksize
        self.alpha = alpha
        self.node = node
        self.nearest = NodeHeap(self.node, self.ksize)
        self.last_ids_crawled: List[str] = []
        self.nearest.push(peers)

        log.info("%s creating spider with %i peers", self.node, len(peers))

    async def _find(self, rpcmethod: F) -> Optional[Union[ValueSpiderFindReturn, NodeSpiderFindReturn]]:
        """
		Make a either a call_find_value or call_find_node rpc to our nearest
		neighbors in attempt to find some node

		Parameters
		-----------
			rpcmethod: F
				The protocol's call_find_value or call_find_node method

		The process:
		  1. calls find_* to current ALPHA nearest not already queried nodes,
			 adding results to current nearest list of k nodes.
		  2. current nearest list needs to keep track of who has been queried
			 already sort by nearest, keep KSIZE
		  3. if list is same as last time, next call should be to everyone not
			 yet queried
		  4. repeat, unless nearest list has all been queried, then ur done

		Returns
		-------
			Optional[ResponseIndexItem]:
				_nodes_found callback, which should be overloaded in sub-classes
		"""
        log.info(
            "%s making find with %s on nearest: %s",
            self.node,
            rpcmethod.__name__,
            ",".join(map(str, self.nearest)),
        )
        count = self.alpha
        if self.nearest.get_ids() == self.last_ids_crawled:
            count = len(self.nearest)
        self.last_ids_crawled = self.nearest.get_ids()

        dicts: Dict[str, Awaitable[Any]] = {}

        for node in self.nearest.get_uncontacted()[:count]:
            if isinstance(node, IndexNode):
                log.warning("Will not execute %s on %s", rpcmethod.__name__, str(node))
                return None

            dicts[node.key] = rpcmethod(node, self.node)
            self.nearest.mark_contacted(node)

        found = await gather_dict(dicts)
        return await self._parse_response_results(found)

    async def _parse_response_results(self, responses: ResponseIndex) -> None:
        """
		A callback to execute once nodes are found via _find
		"""
        raise NotImplementedError


class NodeSpiderCrawl(SpiderCrawl):
    async def find(self) -> Optional[NodeSpiderFindReturn]:
        """
		A wrapper for the base class's _find, where we attempt to find the
		closest node requested using the protocols call_find_node rpc method

		Returns
		-------
		    Optional[PingNodeInfo]
		"""
        return await self._find(self.protocol.call_find_node)  # type: ignore

    async def _parse_response_results(self, responses: ResponseIndex) -> Optional[Union[GenericNode, ResponseIndexItem]]:  # type: ignore
        """
		Handle the result of an iteration in _find.

		Parameters
		----------
			responses: ResponseIndex
				Responses received from peer nodes via NodeCrawl execution

		Returns
		-------
			Optional[Union[GenericNode, ResponseIndexItem]]:
				Recursive call to _find or list of nearest nodes
		"""
        toremove = []
        for peerid, response in responses.items():
            fresponse = RPCFindResponse(response)
            if not fresponse.did_happen() or not fresponse.has_response_item():
                log.debug("%s encountered empty response, removing...", self.node)
                toremove.append(peerid)
            else:
                self.nearest.push(fresponse.get_node_list())  # type: ignore
        self.nearest.remove(toremove)

        if self.nearest.has_exhausted_contacts():
            log.debug("%s has contacted all nearest nodes", self.node)
            return list(self.nearest)  # type: ignore
        return await self.find()  # type: ignore


class ValueSpiderCrawl(SpiderCrawl):
    def __init__(
        self,
        protocol: KademliaProtocol,
        node: GenericNode,
        peers: List[GenericNode],
        ksize: int,
        alpha: int,
    ):
        """
		The C{ValueCrawl}er is basically responsible for executing recursive calls
		to our _find method, which searches our nearest nodes (and the nearest nodes
		to those nodes, so on and so forth) in an attempt to find a given 200-bit
		resource key. This crawler will either return a callback to _handle_found_values
		if values for the given key are found, or the crawler will return None
		if the given key cannot be found via our current node

		Parameters
		----------
			protocol: KademliaProtocol
				A (kademlia) protocol instance.
			node: GenericNode
				representing the key we're looking for
			peers: List[GenericNode]
				A list of instances that provide the entry point for the network
			ksize: int
				The value for k based on the paper
			alpha: int
				The value for alpha based on the paper
		"""
        super(ValueSpiderCrawl, self).__init__(protocol, node, peers, ksize, alpha)

        # keep track of the single nearest node without value - per
        # section 2.3 so we can set the key there if found
        self.nearest_without_value = NodeHeap(self.node, 1)

    async def find(self) -> Optional[ValueSpiderFindReturn]:
        """
		A wrapper for the base class's _find, where we attempt to find the
		closest value requested using the protocols call_find_value rpc method

		Returns
		-------
			Optional[ResponseIndexItem]:
				(1) _find, if we did not find key, but have peers left to search
				(2) None, if we've searched all peers without finding key
				(3) _handle_found_values, if we found values related to our key
		"""
        return await self._find(self.protocol.call_find_value)  # type: ignore

    async def _parse_response_results(self, responses: ResponseIndex) -> Optional[ValueSpiderFindReturn]:  # type: ignore
        """
		Recursively execute a _find and handle all returned values. These values
		can be nodes representing closer nodes to our eventual destination as well
		as the potential values that we've found related to our key

		Parameters
		----------
			responses: ResponseIndex
				Responses from _find

		Returns
		-------
			Optional[ValueSpiderFindReturn]
				Which can be either:
					(1) a recursive call to _find if we have more searching to do
					(2) None, if we've exhausted our search without finding our key
					(3) A call to _handle_found_values if we've found values
		"""
        to_remove: List[str] = []
        found_responses: List[IndexNodeAsDict] = []

        for peer_id, response in responses.items():

            fresponse = RPCFindResponse(response)

            if not fresponse.did_happen():
                to_remove.append(peer_id)
            elif fresponse.has_value():
                found_responses.append(fresponse.item())  # type: ignore
                self.nearest.push(fresponse.get_node_list())  # type: ignore
            else:
                peer = self.nearest.get_node(peer_id)
                if peer:
                    self.nearest_without_value.push([peer])
                    # self.nearest.push(fresponse.get_node_list())

        self.nearest.remove(to_remove)

        if found_responses:
            return await self._handle_found_values(found_responses)

        if self.nearest.has_exhausted_contacts():
            return None

        return await self.find()

    async def _handle_found_values(
        self, items: List[IndexNodeAsDict]
    ) -> Optional[bytes]:
        """
		We got some values!  Exciting. But let's make sure they're all the
		same or freak out a little bit.  Also, make sure we tell the nearest
		node that *didn't* have the value to store it.

		Basically this method is responsible for caching found values closer
		to the current node so as to increase the performance/lookup of
		network operations

		@parameters
            values: List[IndexNodeAsDict]
				Values returned from recursive _find operation

		@returns
            value: Optional[bytes]
				Original value that we were searching for
		"""

        def extract_key(d: IndexNodeAsDict) -> Optional[bytes]:
            key = list(d.keys())[0]
            return d[key]

        flattened = list(map(extract_key, items))  # type: ignore

        value_counts = collections.Counter(flattened)
        if len(value_counts) != 1:
            log.warning("%s multiple values for %s", self.node, value_counts)
            return None

        top_value, _ = value_counts.most_common(1)[0]

        peer = self.nearest_without_value.popleft()
        if peer and isinstance(peer, PingNode):
            log.debug(
                "%s asking nearest node %i to store %s",
                self.node,
                peer.long_id,
                str(top_value),
            )
            top_key = None
            for d in items:
                k, v = list(d.items())[0]
                if v == top_value:
                    top_key = k
                    break

            # TODO: come back and guarantee that top_key will be found
            if not top_key:
                raise RuntimeError("top_key not found here")

            inode = IndexNode(top_key, top_value)
            await self.protocol.call_store(peer, inode)
        return top_value
