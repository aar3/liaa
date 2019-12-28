import logging
from collections import Counter
import asyncio
from typing import List, Any, Dict

from kademlia.node import NodeHeap
from kademlia.rpc import RPCFindResponse
from kademlia.utils import gather_dict

log = logging.getLogger(__name__)  # pylint: disable=invalid-name


# pylint: disable=too-few-public-methods
class SpiderCrawl:
	# pylint: disable=bad-continuation
	def __init__(self,
		protocol: "KademliaProtocol",
		node: "Node",
		peers: List["Node"],
		ksize: int,
		alpha: int
	):
		"""
		The C{SpiderCrawl}er is a base class that is responsible for bootstrapping
		various sub-classes (sub-crawlers) with a list of necessary functions,
		including _find and _nodes_found methods

		Parameters
		-----------
			protocol: KademliaProtocol
				A (kademlia) protocol instance.
			node: Node
				representing the key we're looking for
			peers: List[Node]
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
		self.last_ids_crawled = []
		self.nearest.push(peers)

		log.info("Peer %s creating spider with %i peers", self.node, len(peers))

	async def _find(self, rpcmethod: asyncio.Future) -> asyncio.Future:
		"""
		Make a either a call_find_value or call_find_node rpc to our nearest
		neighbors in attempt to find some node

		Parameters
		-----------
			rpcmethod: asyncio.Future
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
			asyncio.Future:
				_nodes_found callback, which should be overloaded in sub-classes
		"""
		# pylint: disable=bad-continuation
		log.info("Peer %s making find with %s on nearest: %s", self.node,
				rpcmethod.__name__, str(tuple(self.nearest)))
		count = self.alpha
		if self.nearest.get_ids() == self.last_ids_crawled:
			count = len(self.nearest)
		self.last_ids_crawled = self.nearest.get_ids()

		dicts = {}
		for peer in self.nearest.get_uncontacted()[:count]:
			dicts[peer.digest_id] = rpcmethod(peer, self.node)
			self.nearest.mark_contacted(peer)
		found = await gather_dict(dicts)
		return await self._nodes_found(found)

	async def _nodes_found(self, responses):
		"""
		A callback to execute once nodes are found via _find
		"""
		raise NotImplementedError


class ValueSpiderCrawl(SpiderCrawl):
	# pylint: disable=bad-continuation
	def __init__(self,
		protocol: "KademliaProtocol",
		node: "Node",
		peers: List["Node"],
		ksize: int,
		alpha: int
	):
		"""
		The C{ValueCrawl}er is basically responsible for executing recursive calls
		to our _find method, which searches our nearest nodes (and the nearest nodes
		to those nodes, so on and so forth) in an attempt to find a given 160-bit
		resource key. This crawler will either return a callback to _handle_found_values
		if values for the given key are found, or the crawler will return None
		if the given key cannot be found via our current node

		Parameters
		----------
			protocol: KademliaProtocol
				A (kademlia) protocol instance.
			node: Node
				representing the key we're looking for
			peers: List[Node]
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

	async def find(self):
		"""
		A wrapper for the base class's _find, where we attempt to find the
		closest value requested using the protocols call_find_value rpc method
		Returns
		-------
			Optional[Any]:
				Where Any is either:
					(1) _find, if we did not find key, but have peers left to search
					(2) None, if we've searched all peers without finding key
					(3) _handle_found_values, if we found values related to our key
		"""
		return await self._find(self.protocol.call_find_value)

	async def _nodes_found(self, responses: Dict[str, Any]):
		"""
		Recursively execute a _find and handle all returned values. These values
		can be nodes representing closer nodes to our eventual destination as well
		as the potential values that we've found related to our key

		Parameters
		----------
			responses: List[Tuple[bool, Union[List[Tuple[int, str, int]], Dict[str, Any]]]]
				Responses from _find

		Returns
		-------
			Optional[asyncio.Future]
				Which can be either:
					(1) a recursive call to _find if we have more searching to do
					(2) None, if we've exhausted our search without finding our key
					(3) A call to _handle_found_values if we've found values
		"""
		to_remove = []
		found_values = []
		for peer_id, response in responses.items():
			response = RPCFindResponse(response)
			if not response.did_happen():

				# if we did not get a response from the peer in question,
				# we need to remove this peer from our nearest as a way of
				# pruning the network (nodes that don't have resources get
				# lower priority)
				to_remove.append(peer_id)
			elif response.has_value():

				# if we found the value handle it accordingly
				found_values.append(response.get_value())
			else:

				# if we got a response but did not find a value, keep note
				# of this peer not having the value we're searching for, and
				# add this peer's nearest peers to the current node's nearest peers
				peer = self.nearest.get_node(peer_id)
				self.nearest_without_value.push(peer)
				self.nearest.push(response.get_node_list())

		# prune our list of nearest nodes
		self.nearest.remove(to_remove)

		# if our search returned values, handle them
		if found_values:
			return await self._handle_found_values(found_values)

		# if we've contacted all nodes in our binary tree (heapq) and
		# have found no value we do nothing (the network has been updated
		# accordingly already)
		if self.nearest.have_contacted_all():
			return None

		# recursively execute find until we return from either _handle_found_values
		# or from have_contacted_all
		return await self.find()

	async def _handle_found_values(self, values: List[str]):
		"""
		We got some values!  Exciting.  But let's make sure they're all the
		same or freak out a little bit.  Also, make sure we tell the nearest
		node that *didn't* have the value to store it.

		Basically this method is responsible for caching found values closer
		to the current node so as to increase the performance/lookup of
		network operations

		Parameters
		----------
			values: List[str]
				Values returned from recursive _find operation

		Returns
		-------
			value: Any
				Original value that we were searching for
		"""
		value_counts = Counter(values)
		if len(value_counts) != 1:
			log.warning("Peer %s multiple values for %s", self.node, str(values))
		value = value_counts.most_common(1)[0][0]

		peer = self.nearest_without_value.popleft()
		if peer:
			log.debug("Peer %s asking nearest node %i to store %s", self.node, peer.long_id, str(value))
			await self.protocol.call_store(peer, self.node.digest_id, value)
		return value


class NodeSpiderCrawl(SpiderCrawl):
	async def find(self):
		"""
		A wrapper for the base class's _find, where we attempt to find the
		closest node requested using the protocols call_find_node rpc method

		Returns
		-------
			Callable[[Callable[None, Any]], Any]:
				Where Any is either:
					(1) A recursive call to _find
					(2) A call to _nodes_found
					(3) None, if we've searched all peers without finding key
		"""
		return await self._find(self.protocol.call_find_node)

	async def _nodes_found(self, responses: List[Any]) -> asyncio.Future:
		"""
		Handle the result of an iteration in _find.

		Parameters
		----------
			responses: Any
				Responses received from peer nodes via NodeCrawl execution

			Where Any can include:
				List[Tuple[int, str, int]] representing peer nodes
				Dict[str, Any] representing found values

		Returns
		-------
			asyncio.Future:
				Recursive call to _find
		"""
		toremove = []
		for peerid, response in responses.items():
			response = RPCFindResponse(response)
			if not response.did_happen():
				log.debug("Peer %s encountered empty response, removing...", self.node)
				toremove.append(peerid)
			else:
				self.nearest.push(response.get_node_list())
		self.nearest.remove(toremove)

		if self.nearest.have_contacted_all():
			log.debug("Peer %s has contacted all nearest nodes", self.node)
			return list(self.nearest)
		return await self.find()
