import asyncio
import base64
import hashlib
import logging
import sys
import os
import json
import random
from typing import Any, Dict, List, Tuple, Union, Optional

import umsgpack

from liaa.node import Node, PeerNode, ResourceNode
from liaa.routing import RoutingTable
from liaa import __version__
from liaa.utils import join_addr

log = logging.getLogger(__name__)  # pylint: disable=invalid-name

# pylint: disable=too-few-public-methods
class Header:
	Request = b'\x00'
	Response = b'\x01'


class MalformedMessage(Exception):
	pass


class RPCFindResponse:
	def __init__(self, response: List[Dict[str, Any]]):
		"""
		RPCFindResponse

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

		Returns
		-------
			bool:
				Indicator of host response
		"""
		return self.response[0]

	def has_value(self) -> bool:
		"""
		Return whether or not the response has a value

		Returns
		-------
			bool:
				Whether or not the value of the response contains a found value
		"""
		return isinstance(self.response[1], dict)

	def get_value(self) -> Any:
		"""
		Get the value/payload from a response that contains a value

		Returns
		-------
			Any:
				Value of the response payload
		"""
		return self.response[1]['value']

	def get_node_list(self) -> List["PeerNode"]:
		"""
		Get the node list in the response.  If there's no value, this should
		be set.

		Returns
		-------
			List["PeerNode"]:
				List of nodes returned from find response
		"""
		nodelist = self.response[1] or []
		return [PeerNode(key) for key in nodelist]


class RPCDatagramProtocol(asyncio.DatagramProtocol):
	def __init__(self, wait: int = 5):
		"""
		RPCDatagramProtocol

		Protocol implementation using msgpack to encode messages and asyncio
		to handle async sending / recieving.

		Parameters
		----------
			wait: int
				Network connection timeout (default=5)
		"""
		self._wait = wait
		self._outstanding_msgs: Dict[int, Tuple[asyncio.Future, asyncio.Handle]] = {}
		self._queue = {}
		self.transport = None

	def connection_made(self, transport: asyncio.Handle) -> None:
		"""
		Called when a connection is made. (overload from BaseProtocol)

		Parameters
		----------
			transport: asyncio.Handle
				The transport representing the connection. The protocol is
				responsible for storing the reference to its transport
		"""
		self.transport = transport

	def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
		"""
		Called when a datagram is received.

		Parameters
		----------
			data: bytes
				object containing the incoming data.
			addr: Tuple
				address of the peer sending the data; the exact format depends on the transport.
		"""
		log.debug("incoming dgram from peer at %s", join_addr(addr))
		asyncio.ensure_future(self._solve_dgram(data, addr))

	async def _solve_dgram(self, buff: bytes, address: Tuple[str, int]) -> None:
		"""
		Responsible for processing an incoming datagram

		Parameters
		----------
			buff: bytes
				Data to be processed
			address: Tuple
				Address of sending peer
		"""
		if len(buff) < 22:
			log.warning("received invalid dgram from %s, ignoring", address)
			return

		if buff[:1] == Header.Request:
			asyncio.ensure_future(self._accept_request(buff, address))
		elif buff[:1] == Header.Response:
			self._accept_response(buff, address)
		else:
			log.debug("Received unknown message from %s, ignoring", address)

	def _accept_response(self, buff: bytes, address: Tuple[str, int]) -> None:
		"""
		Processor for incoming responses

		Parameters
		----------
			buff: bytes
				Datagram representing incoming message from peer
			address: Tuple
				Address of peer receiving response
		"""
		idf, data = buff[1:21], umsgpack.unpackb(buff[21:])
		msgargs = (base64.b64encode(idf), address)
		if idf not in self._outstanding_msgs:
			log.warning("received unknown message %s from %s; ignoring", *msgargs)
			return

		# pylint: disable=bad-continuation
		log.debug("received %iB response for message id %s from %s", sys.getsizeof(data),
					idf, join_addr(msgargs[1]))

		if not idf in self._queue:
			log.warning("could not mark datagram %s as received", idf)
			return

		fut, timeout = self._queue[idf]
		fut.set_result((True, data))
		timeout.cancel()
		del self._queue[idf]

	async def _accept_request(self, buff: bytes, address: Tuple[str, int]) -> None:
		"""
		Process an incoming request datagram as well as its RPC response

		Parameters
		----------
			buff: bytes
				Datagram representing incoming message from peer
			address: Tuple
				Address of sender
		"""
		idf, data = buff[1:21], umsgpack.unpackb(buff[21:])
		funcname, args = data

		# basically, when we execute an operation such as protocol.ping(), we will
		# send 'ping' as the function name, at which point, we concat 'rpc_' onto
		# the function name so that when we call getattr(self, funcname) we will
		# get the rpc version of the fucname

		func = getattr(self, "rpc_%s" % funcname, None)
		if func is None or not callable(func):
			msgargs = (self.__class__.__name__, funcname)
			log.warning("%s has no callable method rpc_%s; ignoring request", *msgargs)
			return

		if not asyncio.iscoroutinefunction(func):
			func = asyncio.coroutine(func)

		response = await func(address, *args)
		txdata = Header.Response + idf + umsgpack.packb(response)
		# pylint: disable=bad-continuation
		log.debug("sending %iB response for msg id %s to %s", len(txdata),
			base64.b64encode(idf), join_addr(address))
		self.transport.sendto(txdata, address)

	def _timeout(self, msg_id: int) -> None:
		"""
		Make a given datagram timeout

		Parameters
		----------
			msg_id: int
				ID of datagram future to cancel
		"""
		args = (base64.b64encode(msg_id), self._wait)
		log.error("Did not received reply for msg id %s within %i seconds", *args)
		self._outstanding_msgs[msg_id][0].set_result((False, None))
		del self._outstanding_msgs[msg_id]

	def __getattr__(self, name: str) -> Union[asyncio.Future, asyncio.Future, None]:

		if name.startswith("_") or name.startswith("rpc_"):
			return getattr(super(), name)

		try:
			# else we follow normal getattr behavior (same as above)
			return getattr(super(), name)
		except AttributeError:
			pass

		# here we define a catchall function that creates a request using a given
		# function name and *args. these *args are sent and pushed to the msg queue
		# as futures. this closure being called means that we are trying to execute
		# a function name that is not part of the base Kademlia rpc_* protocol
		def func(address, *args):
			msg_id = hashlib.sha1(os.urandom(32)).digest()
			data = umsgpack.packb([name, args])
			if len(data) > 8192:
				log.error("Total length of function name and arguments cannot exceed 8K")
				return None
			txdata = Header.Request + msg_id + data

			# pylint: disable=bad-continuation
			log.debug("Attempting to execute rpc %s on peer at %s - msgid %s",
						name, join_addr(address), base64.b64encode(msg_id))
			self.transport.sendto(txdata, address)

			# we assume python version >= 3.7
			loop = asyncio.get_event_loop()
			future = loop.create_future()
			timeout = loop.call_later(self._wait, self._timeout, msg_id)
			self._queue[msg_id] = (future, timeout)
			self._outstanding_msgs[msg_id] = (future, timeout)
			return future

		return func


class HttpInterface(asyncio.Protocol):
	def __init__(self, source_node: "PeerNode", storage: "IStorage", wait: int = 5):
		"""
		HttpInterface

		Public interface for storing data and fetching data on this server

		Parameters
		----------
			source_node: PeerNode
				Our node (representing the current machine)
			storage: IStorage
				Storage interface
			wait: int
				Timeout of requests
		"""
		self.source_node = source_node
		self.storage = storage
		self.wait = wait
		self.transport = None

	def connection_made(self, transport: asyncio.Handle) -> None:
		"""
		Called when a connection is made. (overload from BaseProtocol)

		Parameters
		----------
			transport: asyncio.Handle
				The transport representing the connection. The protocol is
				responsible for storing the reference to its transport
		"""
		self.transport = transport

	def data_received(self, data: bytes) -> None:
		"""
		Called when in an incoming stream is received.

		Parameters
		----------
			data: bytes
				object containing the incoming data.
		"""
		asyncio.ensure_future(self._handle_data(data))

	async def _handle_data(self, buff: bytes) -> None:
		"""
		Process the incoming stream

		Parameters
		----------
			buff: bytes
				The buffered stream to be process
		"""
		data = buff.decode()
		rawheaders, rawbody = data.split("\r\n\r\n")
		unmarshalled = json.loads(rawbody)

		log.debug("Received new http message %s", data)

		if rawheaders.startswith("GET"):
			response = self.fetch_data(unmarshalled.get("key"))
		elif rawheaders.startswith("PUT"):
			response = self.call_store(rawbody)
		else:
			body = json.dumps({"details": "Not implemented"})
			response = self.pack_response(501, "NOT IMPLEMENTED", body)

		self.transport.write(response.encode())
		self.transport.close()

	def call_store(self, key: str, payload: Optional[bytes]) -> str:
		"""
		Given a payload, save it to storage

		Parameters
		----------
			payload: Optional[bytes]
				Data to be saved

		Returns
		-------
			str:
				Response to write to client
		"""
		node = ResourceNode(key, payload)
		self.storage.set(node)
		return self.pack_response(160, "OK", json.dumps({"details": "ok"}))

	def fetch_data(self, key: Optional[str]) -> str:
		"""
		Given a key, return the its value, if we have the key in storage

		Parameters
		----------
			key: Optional[str]
				Hexkey of the resource to be found

		Returns
		-------
			str:
				Response to write to client
		"""
		node = self.storage.get(key)
		# pylint: disable=bad-continuation
		if node:
			return self.pack_response(160, "OK",
					json.dumps({"details": "found", "data": str(node)}))
		return self.pack_response(404, "NOT FOUND",
				json.dumps({"details": "Not found", "data": str(node)}))

	# pylint: disable=no-self-use
	def pack_response(self, code: int, msg: str, body: Dict[str, str]) -> str:
		"""
		Pack a response's parts into an HTTP message

		Parameters
		----------
			code: int
				Response status code
			msg: str
				Response status message
			body: Dict[str, str]
				Marshalled body payload

		Returns
		-------
			str:
				String-formatted response
		"""
		# pylint: disable=bad-continuation
		headers = [
			f"HTTP/1.1 {msg} {code}",
			f"User-Agent: Liaa.{__version__}",
			"Accept: */*",
			f"Content-Length: {len(body)}",
			f"Content-Type: application/x-www-form-urlencoded",
		]

		return "\r\n".join(headers) + "\r\n\r\n" + body

class KademliaProtocol(RPCDatagramProtocol):
	# pylint: disable=no-self-use,bad-continuation
	def __init__(self, source_node: "PeerNode", storage: "EphemeralStorage", ksize: int):
		"""
		KadmeliaProtocol

		Abstraction used as a layer between our router and storage, and our
		public server. Protocol is responsible for executing various rpc's
		in order to update routing table, storage and keep network active

		Parameters
		----------
			source_node: PeerNode
				Our node (representing the current machine)
			storage: IStorage
				Storage interface
			ksize: int
				Size of kbuckets
		"""
		RPCDatagramProtocol.__init__(self)
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

	def rpc_stun(self, sender: "PeerNode") -> "PeerNode":
		"""
		Execute a S.T.U.N procedure on a given sender

		Parameters
		----------
			sender: PeerNode
				Requesting node

		Returns
		-------
			sender: PeerNode
				Requesting node
		"""
		return sender

	def rpc_ping(self, sender: Tuple[str, int], node_id: str) -> str:
		"""
		Accept an incoming request from sender and return sender's ID
		to indicate a successful ping

		Parameters
		----------
			sender: Tuple
				Address of sender that initiated ping
			node_id: str
				Key of sender that initated ping

		Returns
		-------
			str:
				ID of requesting node
		"""
		source = PeerNode(node_id)
		log.debug("%s got ping request from %s", self.source_node, join_addr(sender))
		self.welcome_if_new(source)
		return self.source_node.key

	def rpc_store(self, sender: "PeerNode", node_id: str, key: str, value: bytes) -> bool:
		"""
		Store data from a given sender

		Parameters
		----------
			sender: PeerNode
				Node that is initiating/requesting store
			node_id: str
				ID of node that is initiating/requesting store
			key: str
				ID of resource to be stored
			value: bytes
				Payload to be stored at `key`

		Returns
		-------
			bool:
				Indicator of successful operation
		"""
		source = Node(join_addr(sender[0], sender[1]))
		self.welcome_if_new(source)
		# pylint: disable=bad-continuation
		log.debug("%s got store request from %s, storing %iB at %s",
					self.source_node, join_addr(sender), len(value), key)
		resource = ResourceNode(key, value)
		self.storage.set(resource)
		return True

	def rpc_find_node(self, sender: "PeerNode", node_id: str, key: str) \
		-> List[Tuple[int, str, int]]:
		"""
		Return a list of peers that are closest to a given key (node_id to be found)

		Parameters
		----------
			sender: PeerNode
				The node initiating the request
			node_id: str
				Node key of the node initiating the request
			key: str
				Key of node who's closes neighbors we want to return

		Returns
		-------
			List[Tuple[int, str, int]]:
				Addresses of closest neighbors in regards to resource `key`
		"""
		source = PeerNode(node_id)
		log.info("%s finding neighbors of %s in local table", self.source_node, source)
		self.welcome_if_new(source)
		node = Node(key, node_type='any', value=None)
		neighbors = self.router.find_neighbors(node, exclude=source)
		return list(map(tuple, neighbors))

	def rpc_find_value(self, sender: "PeerNode", node_id: str, key: str) \
		-> Union[List[Tuple[int, str, int]], Dict[str, Any]]:
		"""
		Return the value at a given key. If the key is found, return it
		to the requestor, else execute an rpc_find_node to find neighbors
		of sender that might have key

		Parameters
		----------
			sender: PeerNode
				Node at which key is stored
			node_id: str
				Key ID of node at which key is stored
			key: str
				ID of resource to be found

		Returns
		-------
			Union[List[Tuple[int, str, int]], Dict[str, Any]]:
				Will be either the given value indexed in a hashmap if the value is
				found, or will recursively attempt to find node at which key is
				stored via calls to `rpc_find_node`
		"""
		source = PeerNode(node_id)
		self.welcome_if_new(source)
		value = self.storage.get(key, None)
		if value is None:
			return self.rpc_find_node(sender, node_id, key)
		return {"value": value}

	async def call_find_node(self, to_ask: "PeerNode", to_find: "Node") -> List[Tuple[int, str, int]]:
		"""
		Dial a given to_ask in order to find to_find

		Parameters
		----------
			to_ask: PeerNode
				Node to ask regarding to_find
			to_find: Node
				Node that this call is attempting to find

		Returns
		-------
			List[Tuple[int, str, int]]:
				Nodes closes to to_find which to continue search
		"""
		address = (to_ask.ip, to_ask.port)
		result = await self.find_node(address, self.source_node.key, to_find.key)
		return self.handle_call_response(result, to_ask)

	async def call_find_value(self, to_ask: "PeerNode", to_find: "Node") \
		-> Union[List[Tuple[int, str, int]], Dict[str, Any]]:
		"""
		Dial a given to_ask in order to find a value on to_find

		Parameters
		----------
			to_ask: PeerNode
				Node to ask in order to find to_find to retrieve a given value
			to_find: Node
				Node that this call is attempting to find

		Returns
		-------
			Union[List[Tuple[int, str, int]], Dict[str, Any]]:
				Either the list of nodes close(r) to the key associated with this
				value, or the actual value
		"""
		address = (to_ask.ip, to_ask.port)
		result = await self.find_value(address, self.source_node.key, to_find.key)
		return self.handle_call_response(result, to_ask)

	async def call_ping(self, to_ask: "PeerNode") -> str:
		"""
		Wrapper for rpc_ping, where we just handle the result

		Parameters
		----------
			to_ask: PeerNode
				Node at which to send ping request

		Returns
		-------
			str:
				ID of peer responding to ping
		"""
		address = (to_ask.ip, to_ask.port)
		result = await self.ping(address, self.source_node.key)
		return self.handle_call_response(result, to_ask)

	async def call_store(self, to_ask: "PeerNode", key: str, value: bytes) -> bool:
		"""
		Wrapper for rpc_store, where we handle the result

		Parameters
		----------
			to_ask: PeerNode
				Node which to ask to store a given key/value pair
			key: str
				ID of resource to store
			value: bytes
				Payload to store at key address

		Returns
		-------
			bool:
				Indication that store operation was succesful
		"""
		address = (to_ask.ip, to_ask.port)
		result = await self.store(address, self.source_node.key, key, value)
		return self.handle_call_response(result, to_ask)

	def welcome_if_new(self, node: "PeerNode"):
		"""
		Given a new node (Peer), send it all the keys/values it should be storing,
		then add it to the routing table.

		Process:
			For each key in storage, get k closest nodes.  If newnode is closer
			than the furtherst in that list, and the node for this server
			is closer than the closest in that list, then store the key/value
			on the new node (per section 2.5 of the paper)

		Parameters
		----------
			node: PeerNode
				Node to add to routing table
		"""
		if not self.router.is_new_node(node) or isinstance(node, ResourceNode):
			return

		log.info("%s welcoming new node %s", self.source_node, node)

		for inode in self.storage:
			neighbors = self.router.find_neighbors(inode)

			if neighbors:
				furthest = neighbors[-1].distance_to(inode)
				is_closer_than_furthest = node.distance_to(inode) < furthest
				closest_distance_to_new = neighbors[0].distance_to(inode)
				curr_distance_to_new = self.source_node.distance_to(inode) < closest_distance_to_new

			if not neighbors or (is_closer_than_furthest and curr_distance_to_new):
				asyncio.ensure_future(self.call_store(node, inode.key, inode.value))

		self.router.add_contact(node)

	def handle_call_response(self, result: Any, node: "PeerNode"):
		"""
		If we get a valid response, welcome the node (if need be). If
		we get no response, remove the node as peer is down

		Parameters
		----------
			result: Any
				Could be the result of any rpc method
			node: PeerNode
				Node to which operation was sent

		Returns
		-------
			result: Any
				The result from our rpc method
		"""
		if not result[0]:
			# pylint: disable=bad-continuation
			log.warning("%s got no response from %s, removing from router",
						self.source_node, node)
			self.router.remove_contact(node)
			return result

		log.info("%s handling successful response from %s", self.source_node, node)
		self.welcome_if_new(node)
		return result
