import logging
from collections import Counter
# pylint: disable=unused-wildcard-import,wildcard-import
from typing import *

from kademlia.node import Node, NodeHeap, TNode
from kademlia.protocol import TKademliaProtocol
from kademlia.utils import gather_dict

log = logging.getLogger(__name__)  # pylint: disable=invalid-name


# pylint: disable=too-few-public-methods
class SpiderCrawl:
	"""
	Crawl the network and look for given 160-bit keys.
	"""
	# pylint: disable=line-too-long
	def __init__(self, protocol: TKademliaProtocol, node: TNode, peers: List[TNode], ksize: int, alpha: int):
		"""
		Create a new C{SpiderCrawl}er.

		Args:
			protocol: A :class:`~kademlia.protocol.KademliaProtocol` instance.
			node: A :class:`~kademlia.node.Node` representing the key we're
				  looking for
			peers: A list of :class:`~kademlia.node.Node` instances that
				   provide the entry point for the network
			ksize: The value for k based on the paper
			alpha: The value for alpha based on the paper
		"""
		self.protocol = protocol
		self.ksize = ksize
		self.alpha = alpha
		self.node = node
		self.nearest = NodeHeap(self.node, self.ksize)
		self.last_ids_crawled = []
		log.info("creating spider with peers: %s", peers)
		self.nearest.push(peers)

	async def _find(self, rpcmethod: Callable[[Any], Optional[Any]]):
		"""
		Get either a value or list of nodes.

		Parameters
		-----------
			rpcmethod: Callable[[Any], Optional[Any]]
				The protocol's call_find_value or call_find_node.

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
			NotImplementedError
		"""
		log.info("crawling network with nearest: %s", str(tuple(self.nearest)))
		count = self.alpha
		if self.nearest.get_ids() == self.last_ids_crawled:
			count = len(self.nearest)
		self.last_ids_crawled = self.nearest.get_ids()

		dicts = {}
		for peer in self.nearest.get_uncontacted()[:count]:
			dicts[peer.id] = rpcmethod(peer, self.node)
			self.nearest.mark_contacted(peer)
		found = await gather_dict(dicts)
		return await self._nodes_found(found)

	async def _nodes_found(self, responses):
		raise NotImplementedError


class ValueSpiderCrawl(SpiderCrawl):
	# pylint: disable=line-too-long
	def __init__(self, protocol: TKademliaProtocol, node: TNode, peers: List[TNode], ksize: int, alpha: int):
		super(ValueSpiderCrawl, self).__init__(protocol, node, peers, ksize, alpha)
		# keep track of the single nearest node without value - per
		# section 2.3 so we can set the key there if found
		self.nearest_without_value = NodeHeap(self.node, 1)

	async def find(self):
		"""
		Find either the closest nodes or the value requested.

		Parameters
		----------
			None

		Returns
		-------
			NotImplementedError
		"""
		return await self._find(self.protocol.call_find_value)

	async def _nodes_found(self, responses: Dict[str, Any]):
		"""
		Handle the result of an iteration in _find.

		Parameters
		----------
			responses: Dict[str, Any]
				Responses from _find

		Returns
		-------
			Optional[NotImplementedError]
		"""
		to_remove = []
		found_values = []
		for peer_id, response in responses.items():
			response = RPCFindResponse(response)
			if not response.did_happen():
				to_remove.append(peer_id)
			elif response.has_value():
				found_values.append(response.get_value())
			else:
				peer = self.nearest.get_node(peer_id)
				self.nearest_without_value.push(peer)
				self.nearest.push(response.get_node_list())
		self.nearest.remove(to_remove)

		if found_values:
			return await self._handle_found_values(found_values)
		if self.nearest.have_contacted_all():
			# not found!
			return None
		return await self.find()

	async def _handle_found_values(self, values):
		"""
		We got some values!  Exciting.  But let's make sure
		they're all the same or freak out a little bit.  Also,
		make sure we tell the nearest node that *didn't* have
		the value to store it.
		"""
		value_counts = Counter(values)
		if len(value_counts) != 1:
			log.warning("Got multiple values for key %i: %s", self.node.long_id, str(values))
		value = value_counts.most_common(1)[0][0]

		peer = self.nearest_without_value.popleft()
		if peer:
			await self.protocol.call_store(peer, self.node.id, value)
		return value


class NodeSpiderCrawl(SpiderCrawl):
	async def find(self):
		"""
		Find the closest nodes.

		Parameters
		----------
			None

		Returns
		-------
			NotImplementedError
		"""
		return await self._find(self.protocol.call_find_node)

	async def _nodes_found(self, responses):
		"""
		Handle the result of an iteration in _find.
		"""
		toremove = []
		for peerid, response in responses.items():
			response = RPCFindResponse(response)
			if not response.did_happen():
				toremove.append(peerid)
			else:
				self.nearest.push(response.get_node_list())
		self.nearest.remove(toremove)

		if self.nearest.have_contacted_all():
			return list(self.nearest)
		return await self.find()


class RPCFindResponse:
	def __init__(self, response):
		"""
		A wrapper for the result of a RPC find.

		Parameters
		----------
			response: Tuple[bool, Union[List[Tuple[int, str, int]], Dict[str, Any]]]
				This will be a tuple of (<response received>, <value>)
				where <value> will be a list of tuples if not found or
				a dictionary of {'value': v} where v is the value desired
		"""
		self.response = response

	def did_happen(self) -> bool:
		"""
		Did the other host actually respond?

		Parameters
		----------
			None

		Returns
		-------
			bool: 
				Indicator of host response
		"""
		return self.response[0]

	def has_value(self) -> bool:
		"""
		Return whether or not the response has a value

		Parameters
		----------
			None

		Returns
		-------
			bool:
				Whether or not the value of the response contains a found value
		"""
		return isinstance(self.response[1], dict)

	def get_value(self) -> Any:
		"""
		Get the value/payload from a response that contains a value

		Parameters
		----------
			None

		Returns
		-------
			Any:
				Value of the response payload
		"""
		return self.response[1]['value']

	def get_node_list(self) -> List[TNode]:
		"""
		Get the node list in the response.  If there's no value, this should
		be set.

		Parameters
		----------
			None

		Returns
		-------
			List[TNode]:
				List of nodes returned from find response
		"""
		nodelist = self.response[1] or []
		return [Node(*nodeple) for nodeple in nodelist]
