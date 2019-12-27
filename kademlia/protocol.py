import asyncio
import logging
import random
# pylint: disable=unused-wildcard-import,wildcard-import
from typing import *

from kademlia.node import Node, NodeType
from kademlia.routing import RoutingTable
from kademlia.rpc import RPCProtocol
from kademlia.utils import hex_to_int, join_addr


log = logging.getLogger(__name__)  # pylint: disable=invalid-name


class KademliaProtocol(RPCProtocol):
	# pylint: disable=no-self-use,bad-continuation
	def __init__(self,
		source_node: "Node",
		storage: "EphemeralStorage",
		ksize: int
	):
		"""
		KadmeliaProtocol

		Abstraction used as a layer between our router and storage, and our
		public server. Protocol is responsible for executing various rpc's
		in order to update routing table, storage and keep network active

		Parameters
		----------
			source_node: Node
				Our node (representing the current machine)
			storage: EphemeralStorage
				Storage interface
			ksize: int
				Size of kbuckets
		"""
		RPCProtocol.__init__(self)
		self.router = RoutingTable(self, ksize, source_node)
		self.storage = storage
		self.source_node = source_node

	def get_refresh_ids(self):
		"""
		Get list of node ids with which to search, in order to keep old
		buckets up to date.

		Returns
		-------
			ids: List[int]
				ids of buckets that have not been updated since 3600
		"""
		ids = []
		for bucket in self.router.lonely_buckets():
			rid = random.randint(*bucket.range).to_bytes(20, byteorder='big')
			ids.append(rid)
		return ids

	def rpc_stun(self, sender: "Node") -> "Node":
		"""
		Execute a S.T.U.N procedure on a given sender

		Parameters
		----------
			sender: Node
				Requesting node

		Returns
		-------
			sender: Node
				Requesting node
		"""
		return sender

	def rpc_ping(self, sender: Tuple[str, int], node_id: int) -> int:
		"""
		Accept an incoming request from sender and return sender's ID
		to indicate a successful ping

		Parameters
		----------
			sender: Tuple
				Address of sender that initiated ping
			node_id: int
				ID of sender that initated ping

		Returns
		-------
			int:
				ID of requesting node
		"""
		source = Node(node_id, sender[0], sender[1])
		log.debug("ping request from %s", join_addr(sender))
		self.welcome_if_new(source)
		return self.source_node.digest_id

	def rpc_store(self, sender: "Node", node_id: int, key: int, value: Any) -> bool:
		"""
		Store data from a given sender

		Parameters
		----------
			sender: Node
				Node that is initiating/requesting store
			node_id: int
				ID of node that is initiating/requesting store
			key: str
				ID of resource to be stored
			value: Any
				Payload to be stored at `key`

		Returns
		-------
			bool:
				Indicator of successful operation
		"""
		source = Node(node_id, sender[0], sender[1])
		self.welcome_if_new(source)
		log.debug("store request from %s, storing %iB at %s", join_addr(sender), len(value), key.hex())
		self.storage[key] = value
		return True

	def rpc_find_node(self,
		sender: "Node",
		node_id: int,
		key: int
	) -> List[Tuple[int, str, int]]:
		"""
		Return a list of peers that are closest to a given key (node_id to be found)

		Parameters
		----------
			sender: Node
				The node initiating the request
			node_id: int
				ID of the node initiating the request
			key: int
				ID node who's closes neighbors we want to return

		Returns
		-------
			List[Tuple[int, str, int]]:
				Addresses of closest neighbors in regards to resource `key`
		"""
		log.info("finding neighbors of %i in local table", hex_to_int(node_id.hex()))
		source = Node(node_id, sender[0], sender[1])
		self.welcome_if_new(source)
		node = Node(key)
		neighbors = self.router.find_neighbors(node, exclude=source)
		return list(map(tuple, neighbors))

	def rpc_find_value(self,
		sender: "Node",
		node_id: int,
		key: int
	) -> Union[List[Tuple[int, str, int]], Dict[str, Any]]:
		"""
		Return the value at a given key. If the key is found, return it
		to the requestor, else execute an rpc_find_node to find neighbors
		of sender that might have key

		Parameters
		----------
			sender: Node
				Node at which key is stored
			node_id: int
				ID of node at which key is stored
			key: int
				ID of resource to be found

		Returns
		-------
			Union[List[Tuple[int, str, int]], Dict[str, Any]]:
				Will be either the given value indexed in a hashmap if the value is
				found, or will recursively attempt to find node at which key is
				stored via calls to `rpc_find_node`
		"""
		source = Node(node_id, sender[0], sender[1])
		self.welcome_if_new(source)
		value = self.storage.get(key, None)
		if value is None:
			return self.rpc_find_node(sender, node_id, key)
		return {"value": value}

	async def call_find_node(self,
		node_to_ask: "Node",
		node_to_find: "Node"
	) -> List[Tuple[int, str, int]]:
		"""
		Dial a given node_to_ask in order to find node_to_find

		Parameters
		----------
			node_to_ask: Node
				Node to ask regarding node_to_find
			node_to_find: Node
				Node that this call is attempting to find

		Returns
		-------
			List[Tuple[int, str, int]]:
				Nodes closes to node_to_find which to continue search
		"""
		address = (node_to_ask.ip, node_to_ask.port)
		result = await self.find_node(address, self.source_node.digest_id, node_to_find.digest_id)
		return self.handle_call_response(result, node_to_ask)

	async def call_find_value(self,
		node_to_ask: "Node",
		node_to_find: "Node"
	) -> Union[List[Tuple[int, str, int]], Dict[str, Any]]:
		"""
		Dial a given node_to_ask in order to find a value on node_to_find

		Parameters
		----------
			node_to_ask: Node
				Node to ask in order to find node_to_find to retrieve a given value
			node_to_find: Node
				Node that this call is attempting to find

		Returns
		-------
			Union[List[Tuple[int, str, int]], Dict[str, Any]]:
				Either the list of nodes close(r) to the key associated with this
				value, or the actual value
		"""
		address = (node_to_ask.ip, node_to_ask.port)
		result = await self.find_value(address, self.source_node.digest_id, node_to_find.id)
		return self.handle_call_response(result, node_to_ask)

	async def call_ping(self, node_to_ask: "Node") -> int:
		"""
		Wrapper for rpc_ping, where we just handle the result

		Parameters
		----------
			node_to_ask: Node
				Node at which to send ping request

		Returns
		-------
			int:
				ID of peer responding to ping
		"""
		address = (node_to_ask.ip, node_to_ask.port)
		result = await self.ping(address, self.source_node.digest_id)
		return self.handle_call_response(result, node_to_ask)

	async def call_store(self, node_to_ask: "Node", key: int, value: Any) -> bool:
		"""
		Wrapper for rpc_store, where we handle the result

		Parameters
		----------
			node_to_ask: Node
				Node which to ask to store a given key/value pair
			key: int
				ID of resource to store
			value: Any
				Payload to store at key address

		Returns
		-------
			bool:
				Indication that store operation was succesful
		"""
		address = (node_to_ask.ip, node_to_ask.port)
		result = await self.store(address, self.source_node.digest_id, key, value)
		return self.handle_call_response(result, node_to_ask)

	def welcome_if_new(self, node: "Node"):
		"""
		Given a new node, send it all the keys/values it should be storing,
		then add it to the routing table.

		Process:
			For each key in storage, get k closest nodes.  If newnode is closer
			than the furtherst in that list, and the node for this server
			is closer than the closest in that list, then store the key/value
			on the new node (per section 2.5 of the paper)

		Parameters
		----------
			node: Node
				Node to add to routing table
		"""
		if not self.router.is_new_node(node):
			return

		log.info("welcoming new node %s, adding to router", node)

		for dkey, value in self.storage:
			keynode = Node(dkey, type=NodeType.Resource, value=value)
			neighbors = self.router.find_neighbors(keynode)
			if neighbors:
				furthest = neighbors[-1].distance_to(keynode)
				is_closer_than_furthest = node.distance_to(keynode) < furthest
				closest_distance_to_new = neighbors[0].distance_to(keynode)
				curr_distance_to_new = self.source_node.distance_to(keynode) < closest_distance_to_new
			if not neighbors or (is_closer_than_furthest and curr_distance_to_new):
				asyncio.ensure_future(self.call_store(node, dkey, value))
		self.router.add_contact(node)

	def handle_call_response(self, result: Any, node: "Node"):
		"""
		If we get a valid response, welcome the node (if need be). If
		we get no response, remove the node as peer is down

		Parameters
		----------
			result: Any
				Could be the result of any rpc method
			node: Node
				Node to which operation was sent

		Returns
		-------
			result: Any
				The result from our rpc method
		"""
		if not result[0]:
			log.warning("no response from %s, removing from router", node)
			self.router.remove_contact(node)
			return result

		log.info("handling successful response from %s", node)
		self.welcome_if_new(node)
		return result
