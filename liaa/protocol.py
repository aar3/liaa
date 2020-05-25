import asyncio
import base64
import hashlib
import logging
import sys
import os
import random
from typing import Any, List, Tuple, Dict, Union, Callable, Optional

import umsgpack  # type: ignore

from liaa.node import Node, NetworkNode, StorageNode
from liaa.storage import EphemeralStorage
from liaa.routing import RoutingTable
from liaa import __version__
from liaa.utils import join_addr

log = logging.getLogger(__name__)  # pylint: disable=invalid-name


# pylint: disable=too-few-public-methods
class Header:
    Request = b"\x00"
    Response = b"\x01"


class MalformedMessage(Exception):
    pass


TResponse = Tuple[bool, Union[List[Tuple[int, str, int]], Dict[str, Any]]]


class RPCFindResponse:
    def __init__(self, response: TResponse):
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

    def get_value(self) -> bytes:
        """
		Get the value/payload from a response that contains a value

		Returns
		-------
			bytes:
				Value of the response payload
		"""
        if isinstance(self.response[1], dict):
            return self.response[1]["value"]

        raise NotImplementedError

    def get_node_list(self) -> List[NetworkNode]:
        """
		Get the node list in the response.  If there's no value, this should
		be set.

		Returns
		-------
			List[NetworkNode]
				List of nodes returned from find response
		"""
        nodelist = self.response[1] or []
        return [NetworkNode(*opt) for opt in nodelist]


class RPCDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, source_node: NetworkNode, wait: int = 5):
        """
		RPCDatagramProtocol

		Protocol implementation using msgpack to encode messages and asyncio
		to handle async sending / recieving.

		Parameters
		----------
			source_node: NetworkNode
				Node on which this protocol is running
			wait: int
				Network connection timeout (default=5)
		"""
        self.source_node = source_node
        self._wait = wait
        self.index: Dict[bytes, Tuple[asyncio.Future, asyncio.Handle]] = {}
        self.transport: Optional[asyncio.BaseTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport):
        """
		Called when a connection is made. (is actually an asyncio.DatagramTransport)

		Overload

		Parameters
		----------
			transport: asyncio.BaseTransport
				The transport representing the connection. The protocol is
				responsible for storing the reference to its transport
		"""
        self.transport = transport

    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        """
		Called when a datagram is received.

		Parameters
		----------
			data: bytes
				object containing the incoming data.
			addr: Tuple
				address of the peer sending the data; the exact format depends on the transport.
		"""
        # pylint: disable=bad-continuation
        log.debug(
            "%s got incoming dgram from peer at %s",
            str(self.source_node),
            join_addr(addr),
        )
        asyncio.ensure_future(self._solve_dgram(data, addr))

    async def _solve_dgram(self, byte_arr: bytes, address: Tuple[str, int]):
        """
		Responsible for processing an incoming datagram

		Parameters
		----------
			byte_arr: bytes
				Data to be processed
			address: Tuple[str, int]
				Address of sending peer
		"""
        if len(byte_arr) < 22:
            log.warning(
                "%s received invalid dgram from %s, ignoring",
                str(self.source_node),
                address,
            )
            return

        if byte_arr[:1] == Header.Request:
            asyncio.ensure_future(self._accept_request(byte_arr, address))
        elif byte_arr[:1] == Header.Response:
            self._accept_response(byte_arr, address)
        else:
            log.debug("Received unknown message from %s, ignoring", address)

    def _accept_response(self, byte_arr: bytes, address: Tuple[str, int]):
        """
		Processor for incoming responses

		Parameters
		----------
			byte_arr: bytes
				Datagram representing incoming message from peer
			address: Tuple[str, int]
				Address of peer receiving response
		"""
        idf, data = byte_arr[1:21], umsgpack.unpackb(byte_arr[21:])
        msgargs = (base64.b64encode(idf), address)

        if not idf in self.index:
            log.warning(
                "%s could not mark datagram %s as received", str(self.source_node), idf
            )
            return

        log.debug(
            "%s %iB response for message id %s from %s",
            str(self.source_node),
            sys.getsizeof(data),
            idf,
            join_addr(msgargs[1]),
        )

        fut, timeout = self.index[idf]
        fut.set_result((True, data))
        timeout.cancel()

        del self.index[idf]

    async def _accept_request(self, byte_arr: bytes, address: Tuple[str, int]):
        """
		Process an incoming request datagram as well as its RPC response

		Parameters
		----------
			byte_arr: bytes
				Datagram representing incoming message from peer
			address: Tuple[str, int]
				Address of sender
		"""
        idf, data = byte_arr[1:21], umsgpack.unpackb(byte_arr[21:])
        funcname, args = data

        # when we execute an operation such as protocol.ping(), we will
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

        log.debug(
            "%s sending %iB response for msg id %s to %s",
            str(self.source_node),
            len(txdata),
            base64.b64encode(idf),
            join_addr(address),
        )
        self.transport.sendto(txdata, address)  # type: ignore

    def _timeout(self, msg_id: bytes):
        """
		Make a given datagram timeout

		Parameters
		----------
			msg_id: bytes
				ID of datagram future to cancel
		"""
        args = (base64.b64encode(msg_id), self._wait)
        log.error("Did not received reply for msg id %s within %i seconds", *args)
        self.index[msg_id][0].set_result((False, None))
        del self.index[msg_id]

    def __getattr__(self, name: str) -> Callable[..., asyncio.Future]:

        if name.startswith("_") or name.startswith("rpc_"):
            return getattr(super(), name)

        try:
            # else we follow normal getattr behavior (same as above)
            return getattr(super(), name)
        except AttributeError:
            pass

        # here we define a catchall function that creates a request using a given
        # function name and *args. these *args are sent and pushed to the msg index
        # as futures. this closure being called means that we are trying to execute
        # a function name that is not part of the base Kademlia rpc_* protocol
        def func(address, *args):
            msg_id = hashlib.sha1(os.urandom(32)).digest()
            data = umsgpack.packb([name, args])
            if len(data) > 8192:
                log.error(
                    "Total length of function name and arguments cannot exceed 8K"
                )
                return None
            txdata = Header.Request + msg_id + data

            # pylint: disable=bad-continuation
            log.debug(
                "Attempting to execute rpc %s on peer at %s - msgid %s",
                name,
                join_addr(address),
                base64.b64encode(msg_id),
            )
            self.transport.sendto(txdata, address)  # type: ignore

            # we assume python version >= 3.7
            loop = asyncio.get_event_loop()
            future = loop.create_future()
            timeout = loop.call_later(self._wait, self._timeout, msg_id)
            self.index[msg_id] = (future, timeout)
            return future

        return func


class KademliaProtocol(RPCDatagramProtocol):
    def __init__(self, source_node: NetworkNode, storage: EphemeralStorage, ksize: int):
        """
		KadmeliaProtocol

		Abstraction used as a layer between our router and storage, and our
		public server. Protocol is responsible for executing various rpc's
		in order to update routing table, storage and keep network active

		Parameters
		----------
			source_node: NetworkNode
				Our node (representing the current machine)
			storage: EphemeralStorage
				Storage interface
			ksize: int
				Size of kbuckets
		"""
        super(KademliaProtocol, self).__init__(source_node)
        self.router = RoutingTable(self, ksize, source_node)
        self.storage = storage
        self.source_node = source_node

    def get_refresh_ids(self) -> List[Node]:
        """
		Get random node ids for buckets that haven't been updated in an hour

		Returns
		-------
			ids: List[NetworNode]
				Key ids of buckets that have not been updated since 3600
		"""
        ids: List[Node] = []
        for bucket in self.router.lonely_buckets():
            rid = random.choice(bucket.get_set())
            ids.append(rid)
        return ids

    def rpc_stun(self, sender: NetworkNode) -> NetworkNode:
        """
		Execute a S.T.U.N procedure on a given sender

		Parameters
		----------
			sender: NetworkNode
				Requesting node

		Returns
		-------
			sender: NetworkNode
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
				key id of requesting node
		"""
        source = NetworkNode(node_id)
        log.debug("%s got ping request from %s", self.source_node, join_addr(sender))
        self.welcome_if_new(source)
        return self.source_node.key

    # pylint: disable=unused-argument
    def rpc_store(self, sender: NetworkNode, key: str, value: bytes) -> bool:
        """
		Store data from a given sender

		Parameters
		----------
			sender: NetworkNode
				Node that is initiating/requesting store
			key: str
				ID of resource to be stored
			value: bytes
				Payload to be stored at `key`

		Returns
		-------
			bool:
				Indicator of successful operation
		"""
        self.welcome_if_new(sender)
        log.debug(
            "%s got store request from %s, storing %iB at %s",
            self.source_node,
            sender.key,
            len(value),
            key,
        )
        node = StorageNode(key, value)
        self.storage.set(node)
        return True

    def rpc_find_node(self, sender, node_id, key):
        """
		Return a list of nodes that are closest to a given key (node_id to be found)

		Parameters
		----------
			sender: NetworkNode
				The node initiating the request
			node_id: str
				Node key of the node initiating the request
			key: str
				Key of node who's closes neighbors we want to return

		Returns
		-------
			Tuple representations of closest neighbors in regards to `key`
			which will be either Tuple[str, str, int] if node is a peer or,
			Tuple[str, None, Optional[bytes]] if node is resource
		"""
        source = NetworkNode(node_id)
        log.info("%s finding neighbors of %s in local table", self.source_node, source)
        self.welcome_if_new(source)
        node = Node(key)
        neighbors = self.router.find_neighbors(node, exclude=source)
        return list(map(tuple, neighbors))

    def rpc_find_value(self, sender, node_id, key):
        """
		Return the value at a given key. If the key is found, return it
		to the requestor, else execute an rpc_find_node to find neighbors
		of sender that might have key

		Parameters
		----------
			sender: NetworkNode
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
        source = NetworkNode(node_id)
        self.welcome_if_new(source)
        value = self.storage.get(key)
        if value is None:
            return self.rpc_find_node(sender, node_id, key)
        return {"value": value}

    async def call_find_node(self, to_ask, to_find):
        """
		Dial a given to_ask in order to find to_find

		Parameters
		----------
			to_ask: NetworkNode
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

    async def call_find_value(self, to_ask, to_find):
        """
		Dial a given to_ask in order to find a value on to_find

		Parameters
		----------
			to_ask: NetworkNode
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

    async def call_ping(self, to_ask):
        """
		Wrapper for rpc_ping, where we just handle the result

		Parameters
		----------
			to_ask: NetworkNode
				Node at which to send ping request

		Returns
		-------
			str:
				ID of peer responding to ping
		"""
        address = (to_ask.ip, to_ask.port)
        result = await self.ping(address, self.source_node.key)
        return self.handle_call_response(result, to_ask)

    async def call_store(self, to_ask, key, value):
        """
		Wrapper for rpc_store, where we handle the result

		Parameters
		----------
			to_ask: NetworkNode
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

    def welcome_if_new(self, node):
        """
		Section 2.5

		Given a new node (Peer), send it all the keys/values it should be storing,
		then add it to the routing table.

		Process:
			For each key in storage, get k closest nodes.  If newnode is closer
			than the furtherst in that list, and the node for this server
			is closer than the closest in that list, then store the key/value
			on the new node

		Parameters
		----------
			node: NetworkNode
				Node to add to routing table
		"""
        # because we can only call_store on peers
        if not self.router.is_new_node(node) or isinstance(node, StorageNode):
            return

        log.info("%s welcoming new node %s", self.source_node, node)

        for inode in self.storage:
            neighbors = self.router.find_neighbors(inode)

            if neighbors:
                furthest = neighbors[-1].distance_to(inode)
                is_closer_than_furthest = node.distance_to(inode) < furthest
                closest_distance_to_new = neighbors[0].distance_to(inode)
                curr_distance_to_new = (
                    self.source_node.distance_to(inode) < closest_distance_to_new
                )

            if not neighbors or (is_closer_than_furthest and curr_distance_to_new):
                asyncio.ensure_future(self.call_store(node, inode.key, inode.value))

        # entry point for all nodes in the network to our router
        self.router.add_contact(node)

    def handle_call_response(self, result, node):
        """
		If we get a valid response, welcome the node (if need be). If
		we get no response, remove the node as peer is down

		Parameters
		----------
			result: Any
				Could be the result of any rpc method
			node: NetworkNode
				Node to which operation was sent

		Returns
		-------
			result: Any
				The result from our rpc method
		"""
        if not result[0]:
            # pylint: disable=bad-continuation
            log.warning(
                "%s got no response from %s, removing from router",
                self.source_node,
                node,
            )
            self.router.remove_contact(node)
            return result

        log.info("%s handling successful response from %s", self.source_node, node)
        self.welcome_if_new(node)
        return result
