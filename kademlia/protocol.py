import os
import asyncio
import logging
import random
from base64 import b64encode
from hashlib import sha1

import umsgpack

from kademlia.node import Node
from kademlia.routing import RoutingTable
from kademlia.utils import digest

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


class Datagram:
	def __init__(self, buff):
		self.buff = buff or []
		self.action = self.buff[:1]
		# pylint: disable=invalid-name
		self.id = self.buff[1:21]
		self.data = umsgpack.unpackb(self.buff[21:])

		if self.has_valid_len() and not self.is_malformed():
			self.funcname, self.args = self.data

	def has_valid_len(self):
		# if len(dgram) < 22, then there isnt enough data to unpack
		# a request/response byte, and a msg id
		return len(self.buff) >= 22

	def is_malformed(self):
		return not isinstance(self.data, list) or len(self.data) != 2


class MalformedMessage(Exception):
	pass


class RPCProtocol(asyncio.DatagramProtocol):
	"""
	Protocol implementation using msgpack to encode messages and asyncio
	to handle async sending / recieving.
	"""
	def __init__(self, wait=5):
		"""
		Create a protocol instance.

		Args:
			wait (int): Time to wait for a response before giving up
		"""
		self._wait = wait
		self._outstanding_msgs = {}
		self._queue = RPCMessageQueue()
		self.transport = None

	def connection_made(self, transport):
		self.transport = transport

	def dgram_received(self, data, addr):
		log.debug("received dgram from %s", addr)
		asyncio.ensure_future(self._solve_dgram(data, addr))

	async def _solve_dgram(self, buff, address):
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

	def _accept_response(self, dgram, address):
		msgargs = (b64encode(dgram.id), address)
		if dgram.id not in self._outstanding_msgs:
			log.warning("received unknown message %s from %s; ignoring", *msgargs)
			return

		log.debug("received response %s for message id %s from %s", dgram.data, *msgargs)
		if not self._queue.dequeue_fut(dgram):
			log.warning("could not mark datagram %s as received", dgram.id)

	async def _accept_request(self, dgram, address):
		if dgram.is_malformed():
			raise MalformedMessage("Could not read packet: %s" % dgram.data)

		# these rpc_* functions will be implemented in sub-classes - be warned,
		# this uses a bit of pythonic magic - TODO: consider explicit refactor
		func = getattr(self, "rpc_%s" % dgram.funcname, None)
		if func is None or not callable(func):
			msgargs = (self.__class__.__name__, dgram.funcname)
			log.warning("%s has no callable method rpc_%s; ignoring request", *msgargs)
			return

		if not asyncio.iscoroutinefunction(func):
			func = asyncio.coroutine(func)

		response = await func(address, *dgram.args)
		log.debug("sending response %s for msg id %s to %s", response, b64encode(dgram.id), address)
		txdata = Header.Response + dgram.id + umsgpack.packb(response)
		self.transport.sendto(txdata, address)

	def _timeout(self, msg_id):
		args = (b64encode(msg_id), self._wait)
		log.error("Did not received reply for msg id %s within %i seconds", *args)
		self._outstanding_msgs[msg_id][0].set_result((False, None))
		del self._outstanding_msgs[msg_id]

	def __getattr__(self, name):
		"""
		If name begins with "_" or "rpc_", returns the value of
		the attribute in question as normal.

		Otherwise, returns the value as normal *if* the attribute
		exists, but does *not* raise AttributeError if it doesn't.

		Instead, returns a closure, func, which takes an argument
		"address" and additional arbitrary args (but not kwargs).

		func attempts to call a remote method "rpc_{name}",
		passing those args, on a node reachable at address.
		"""
		if name.startswith("_") or name.startswith("rpc_"):
			return getattr(super(), name)

		try:
			return getattr(super(), name)
		except AttributeError:
			pass

		# here we define a function that creates a request using function name
		# `name` and `*args`, sends it, and pushes it to the msg queue
		def func(address, *args):
			msg_id = sha1(os.urandom(32)).digest()
			data = umsgpack.packb([name, args])
			if len(data) > MAX_PAYLOAD_SIZE:
				raise MalformedMessage("Total length of function name and arguments cannot exceed 8K")
			txdata = Header.Request + msg_id + data
			log.debug("calling remote function %s on %s (msgid %s)", name, address, b64encode(msg_id))
			self.transport.sendto(txdata, address)

			# we assume python version >= 3.7
			loop = asyncio.get_event_loop()
			future = loop.create_future()
			timeout = loop.call_later(self._wait, self._timeout, msg_id)
			self._queue.enqueue_fut(msg_id, future, timeout)
			return future

		return func


class KademliaProtocol(RPCProtocol):
	def __init__(self, source_node, storage, ksize):
		RPCProtocol.__init__(self)
		self.router = RoutingTable(self, ksize, source_node)
		self.storage = storage
		self.source_node = source_node

	def get_refresh_ids(self):
		"""
		Get list of node ids with which to search, in order to keep old
		buckets up to date.
		"""
		ids = []
		for bucket in self.router.lonely_buckets():
			rid = random.randint(*bucket.range).to_bytes(20, byteorder='big')
			ids.append(rid)
		return ids

	def rpc_stun(self, sender):  # pylint: disable=no-self-use
		return sender

	def rpc_ping(self, sender, nodeid):
		source = Node(nodeid, sender[0], sender[1])
		self.welcome_if_new(source)
		return self.source_node.id

	def rpc_store(self, sender, nodeid, key, value):
		source = Node(nodeid, sender[0], sender[1])
		self.welcome_if_new(source)
		log.debug("got a store request from %s, storing '%s'='%s'", sender, key.hex(), value)
		self.storage[key] = value
		return True

	def rpc_find_node(self, sender, nodeid, key):
		log.info("finding neighbors of %i in local table", int(nodeid.hex(), 16))
		source = Node(nodeid, sender[0], sender[1])
		self.welcome_if_new(source)
		node = Node(key)
		neighbors = self.router.find_neighbors(node, exclude=source)
		return list(map(tuple, neighbors))

	def rpc_find_value(self, sender, nodeid, key):
		source = Node(nodeid, sender[0], sender[1])
		self.welcome_if_new(source)
		value = self.storage.get(key, None)
		if value is None:
			return self.rpc_find_node(sender, nodeid, key)
		return {'value': value}

	async def call_find_node(self, node_to_ask, node_to_find):
		address = (node_to_ask.ip, node_to_ask.port)
		result = await self.find_node(address, self.source_node.id, node_to_find.id)
		return self.handle_call_response(result, node_to_ask)

	async def call_find_value(self, node_to_ask, node_to_find):
		address = (node_to_ask.ip, node_to_ask.port)
		result = await self.find_value(address, self.source_node.id, node_to_find.id)
		return self.handle_call_response(result, node_to_ask)

	async def call_ping(self, node_to_ask):
		address = (node_to_ask.ip, node_to_ask.port)
		result = await self.ping(address, self.source_node.id)
		return self.handle_call_response(result, node_to_ask)

	async def call_store(self, node_to_ask, key, value):
		address = (node_to_ask.ip, node_to_ask.port)
		result = await self.store(address, self.source_node.id, key, value)
		return self.handle_call_response(result, node_to_ask)

	def welcome_if_new(self, node):
		"""
		Given a new node, send it all the keys/values it should be storing,
		then add it to the routing table.

		@param node: A new node that just joined (or that we just found out
		about).

		Process:
		For each key in storage, get k closest nodes.  If newnode is closer
		than the furtherst in that list, and the node for this server
		is closer than the closest in that list, then store the key/value
		on the new node (per section 2.5 of the paper)
		"""
		if not self.router.is_new_node(node):
			return

		log.info("never seen %s before, adding to router", node)
		for key, value in self.storage:
			keynode = Node(digest(key))
			neighbors = self.router.find_neighbors(keynode)
			if neighbors:
				last = neighbors[-1].distance_to(keynode)
				new_node_close = node.distance_to(keynode) < last
				first = neighbors[0].distance_to(keynode)
				this_closest = self.source_node.distance_to(keynode) < first
			if not neighbors or (new_node_close and this_closest):
				asyncio.ensure_future(self.call_store(node, key, value))
		self.router.add_contact(node)

	def handle_call_response(self, result, node):
		"""
		If we get a response, add the node to the routing table.  If
		we get no response, make sure it's removed from the routing table.
		"""
		if not result[0]:
			log.warning("no response from %s, removing from router", node)
			self.router.remove_contact(node)
			return result

		log.info("got successful response from %s", node)
		self.welcome_if_new(node)
		return result
