import asyncio
import base64
import hashlib
import logging
import os
from typing import Any, List, Dict, Tuple, Union

import umsgpack

from kademlia.node import Node
from kademlia.exception import MalformedMessage
from kademlia.utils import join_addr

log = logging.getLogger(__name__)  # pylint: disable=invalid-name

MAX_PAYLOAD_SIZE = 8192

# pylint: disable=too-few-public-methods
class Header:
	Request = b'\x00'
	Response = b'\x01'


class RPCMessageQueue:
	def __init__(self):
		self.items = {}

	def remove_item(self, msg_id):
		del self.items[msg_id]

	def enqueue_fut(self, msg_id, fut, timeout):
		self.items[msg_id] = (fut, timeout)

	def get_fut(self, msg_id):
		return self.items[msg_id]

	def dequeue_fut(self, dgram):
		if not dgram.id in self:
			return False
		fut, timeout = self.get_fut(dgram.id)
		fut.set_result((True, dgram.data))
		timeout.cancel()
		del self.items[dgram.id]
		return True

	def __contains__(self, key):
		return key in self.items

	def __len__(self):
		return len(self.items)


class RPCFindResponse:
	def __init__(self, response):
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

	def get_node_list(self) -> List["Node"]:
		"""
		Get the node list in the response.  If there's no value, this should
		be set.
		Returns
		-------
			List["Node"]:
				List of nodes returned from find response
		"""
		nodelist = self.response[1] or []
		return [Node(*nodeple) for nodeple in nodelist]


class Datagram:
	"""
	Datagram

	A wrapper over a byte array that is used to represent data
	passed to and from each peer in the network
	"""
	def __init__(self, buff: bytes):
		self.buff = buff or []
		self.action = self.buff[:1]
		# pylint: disable=invalid-name
		self.id = self.buff[1:21]
		self.data = umsgpack.unpackb(self.buff[21:])

		if self.has_valid_len() and not self.is_malformed():
			self.funcname, self.args = self.data

	def has_valid_len(self) -> bool:
		"""
		Determine if a datagram's buffer is long enough to be processed

		If len(dgram) < 22, then there isnt enough data to unpack a
		request/response byte, and a msg id
		Returns
		-------
			bool
		"""
		return len(self.buff) >= 22

	def is_malformed(self) -> bool:
		"""
		Determine if a datagram is invalid/corrupted by seeing if its
		data is a byte array, as well as whether or not is data consists
		of two parts - a RPC function name, and RPC function args



		Return
		------
			None
		"""
		return not isinstance(self.data, list) or len(self.data) != 2


class RPCProtocol(asyncio.DatagramProtocol):
	def __init__(self, wait: int = 5):
		"""
		RPCProtocol

		Protocol implementation using msgpack to encode messages and asyncio
		to handle async sending / recieving.

		Parameters
		----------
			wait: int
				Network connection timeout (default=5)
		"""
		self._wait = wait
		self._outstanding_msgs: Dict[int, Tuple[asyncio.Future, asyncio.Handle]] = {}
		self._queue = RPCMessageQueue()
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

	def datagram_received(self, data: Tuple[str, bytes], addr: Tuple[str, int]) -> None:
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
		dgram = Datagram(buff)

		if not dgram.has_valid_len():
			log.warning("received invalid dgram from %s, ignoring", address)
			return

		if dgram.action == Header.Request:
			asyncio.ensure_future(self._accept_request(dgram, address))
		elif dgram.action == Header.Response:
			self._accept_response(dgram, address)
		else:
			log.debug("Received unknown message from %s, ignoring", address)

	def _accept_response(self, dgram: "Datagram", address: Tuple[str, int]) -> None:
		"""
		Processor for incoming responses

		Parameters
		----------
			dgram: Datagram
				Datagram representing incoming message from peer
			address: Tuple
				Address of peer receiving response


		"""
		msgargs = (base64.b64encode(dgram.id), address)
		if dgram.id not in self._outstanding_msgs:
			log.warning("received unknown message %s from %s; ignoring", *msgargs)
			return

		log.debug("received response %s for message id %s from %s", dgram.data, dgram.id, join_addr(msgargs))
		if not self._queue.dequeue_fut(dgram):
			log.warning("could not mark datagram %s as received", dgram.id)

	async def _accept_request(self, dgram: "Datagram", address: Tuple[str, int]) -> None:
		"""
		Process an incoming request datagram as well as its RPC response

		Parameters
		----------
			dgram: Datagram
				Incoming datagram used to identify peer, process request, and pass
				sending peer's data
			address: Tuple
				Address of sender


		"""
		if dgram.is_malformed():
			raise MalformedMessage("Could not read packet: %s" % dgram.data)

		# basically, when we execute an operation such as protocol.ping(), we will
		# send 'ping' as the function name, at which point, we concat 'rpc_' onto
		# the function name so that when we call getattr(self, funcname) we will
		# get the rpc version of the fucname

		# FIXME: explore if there is a more explicit, non-hackish way to execute
		# these rpc methods

		func = getattr(self, "rpc_%s" % dgram.funcname, None)
		if func is None or not callable(func):
			msgargs = (self.__class__.__name__, dgram.funcname)
			log.warning("%s has no callable method rpc_%s; ignoring request", *msgargs)
			return

		if not asyncio.iscoroutinefunction(func):
			func = asyncio.coroutine(func)

		response = await func(address, *dgram.args)
		# pylint: disable=bad-continuation
		log.debug("sending response %s for msg id %s to %s", response,
			base64.b64encode(dgram.id), join_addr(address))
		txdata = Header.Response + dgram.id + umsgpack.packb(response)
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
			if len(data) > MAX_PAYLOAD_SIZE:
				raise MalformedMessage("Total length of function name and arguments cannot exceed 8K")
			txdata = Header.Request + msg_id + data
			log.debug("executing rpc %s on %s (msgid %s)", name, join_addr(address), base64.b64encode(msg_id))
			self.transport.sendto(txdata, address)

			# we assume python version >= 3.7
			loop = asyncio.get_event_loop()
			future = loop.create_future()
			timeout = loop.call_later(self._wait, self._timeout, msg_id)
			self._queue.enqueue_fut(msg_id, future, timeout)
			self._outstanding_msgs[msg_id] = (future, timeout)
			return future

		return func
