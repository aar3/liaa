"""
Package for interacting on the network at a high level.
"""
import random
import pickle
import asyncio
import logging
from typing import List, Tuple, Union, Optional, Any

from kademlia.protocol import KademliaProtocol, TKademliaProtocol
from kademlia.utils import digest
from kademlia.storage import ForgetfulStorage
from kademlia.node import Node, TNode, Resource
from kademlia.crawling import ValueSpiderCrawl, NodeSpiderCrawl


log = logging.getLogger(__name__)  # pylint: disable=invalid-name


# pylint: disable=too-many-instance-attributes
class Server:

	protocol_class = KademliaProtocol

	def __init__(self, ksize=20, alpha=3, node_id=None, storage=None):
		"""
		High level view of a node instance.  This is the object that should be
		created to start listening as an active node on the network.
		Create a server instance.  This will start listening on the given port.

		Parameters
		----------
			ksize: int
				The k parameter from the paper
			alpha: int
				The alpha parameter from the paper
			node_id: int
				The id for this node on the network.
			storage: ForgetfulStorage
				A storage interface
		"""
		self.ksize = ksize
		self.alpha = alpha
		self.storage = storage or ForgetfulStorage()
		self.node = Node(node_id or digest(random.getrandbits(255)))
		self.transport = None
		self.protocol = None
		self.refresh_loop = None
		self.save_state_loop = None

	def stop(self) -> None:
		"""
		Stop a currently running server - all event loops, and close
		all open network connections

		Parameters
		----------
			None

		Returns
		-------
			None
		"""
		if self.transport is not None:
			self.transport.close()

		if self.refresh_loop:
			self.refresh_loop.cancel()

		if self.save_state_loop:
			self.save_state_loop.cancel()

	def _create_protocol(self) -> TKademliaProtocol:
		"""
		Create an instance of the Kademlia protocol

		Parameters
		----------
			None

		Returns
		-------
			KademliaProtocol:
				Instance of the kademlia protocol
		"""
		return self.protocol_class(self.node, self.ksize)

	async def listen(self, port: int, interface='0.0.0.0') -> None:
		"""
		Start our datagram endpoint listening on the given port
		Provide interface="::" to accept ipv6 address

		Parameters
		----------
			port: int
				Port on which to listen
			interface: str
				Interface on which to bind port

		Returns
		-------
			None
		"""
		loop = asyncio.get_event_loop()
		listen = loop.create_datagram_endpoint(self._create_protocol, local_addr=(interface, port))
		log.info("Node %i listening on %s:%i", self.node.long_id, interface, port)
		self.transport, self.protocol = await listen
		# finally, schedule refreshing table
		self.refresh_table()

	def refresh_table(self, delay=3600) -> None:
		"""
		Refresh our routing table via a

		Parameters
		----------
			delay: int
				Time to wait (secs) before executing future

		Returns
		-------
			None
		"""
		log.debug("Refreshing routing table")
		asyncio.ensure_future(self._refresh_table())
		loop = asyncio.get_event_loop()
		self.refresh_loop = loop.call_later(delay, self.refresh_table)

	async def _refresh_table(self) -> None:
		"""
		Refresh buckets that haven't had any lookups in the last hour
		(per section 2.3 of the paper).

		Parameters
		----------
			None

		Returns
		-------
			None
		"""
		results: List[asyncio.Future] = []
		for node_id in self.protocol.get_refresh_ids():
			node = Node(node_id)
			nearest = self.protocol.router.find_neighbors(node, self.alpha)
			spider = NodeSpiderCrawl(self.protocol, node, nearest, self.ksize, self.alpha)
			results.append(spider.find())

		# do our crawling
		await asyncio.gather(*results)

		# now republish keys older than one hour
		for dkey, value in self.storage.iter_older_than(3600):
			await self.set_digest(dkey, value)

	def bootstrappable_neighbors(self) -> List[TNode]:
		"""
		Get a list of (ip, port) tuple pairs suitable for use as an argument to
		the bootstrap method.

		The server should have been bootstrapped
		already - this is just a utility for getting some neighbors and then
		storing them if this server is going down for a while.  When it comes
		back up, the list of nodes can be used to bootstrap.

		Parameters
		----------
			None

		Returns
		-------
			List[TNode]:
				List of peers suitable for bootstrap use
		"""
		neighbors: List[TNode] = self.protocol.router.find_neighbors(self.node)
		return [tuple(n)[-2:] for n in neighbors]

	async def bootstrap(self, addrs) -> asyncio.Future:
		"""
		Bootstrap the server by connecting to other known nodes in the network.

		Parameters
		----------
			addrs: List[Tuple[str, int]]
				Note that only IP addresses are acceptable - hostnames will
				cause an error.

		Returns
		-------
			asyncio.Future:
				scheduled callback for a NodeSpiderCrawl to continue crawling
				network in order to find peers for self.node
		"""
		log.debug("Attempting to bootstrap node with %i initial contacts", len(addrs))
		cos = list(map(self.bootstrap_node, addrs))
		gathered = await asyncio.gather(*cos)
		nodes = [node for node in gathered if node is not None]
		spider = NodeSpiderCrawl(self.protocol, self.node, nodes, self.ksize, self.alpha)
		return await spider.find()

	async def bootstrap_node(self, addr: Tuple[str, int]) -> Optional[TNode]:
		"""
		Ping a given address so that both `addr` and `self.node` can know
		about one another

		Parameters
		----------
			addr: Tuple[str, int]
				Address of peer to ping

		Returns
		-------
			Optiona[Node]:
				None if ping was unsuccessful, or peer as Node if ping
				was successful
		"""
		result = await self.protocol.ping(addr, self.node.id)
		return Node(result[1], addr[0], addr[1]) if result[0] else None

	async def get(self, key: Union[str, bytes]) -> asyncio.Future:
		"""
		Crawl the current node's known network in order to find a given key. This
		is the interface for grabbing a key from the network

		Parameters
		----------
			key: Union[str, bytes]
				Key to find in network

		Returns
		-------
			asyncio.Future:
				A recursive call to ValueSpiderCrawl.find which will terminate
				either when the value is find or the search is exhausted
		"""
		log.info("Looking up key %s", key)
		dkey = digest(key)
		# if this node has it, return it
		if self.storage.get(dkey) is not None:
			return self.storage.get(dkey)
		rsrc = Resource(dkey)
		nearest = self.protocol.router.find_neighbors(rsrc)
		if not nearest:
			log.warning("There are no known neighbors to get key %s", key)
			return None
		spider = ValueSpiderCrawl(self.protocol, rsrc, nearest, self.ksize, self.alpha)
		return await spider.find()

	async def set(self, key: Union[bytes, str], value: Any) -> asyncio.Future:
		"""
		Set the given string key to the given value in the network. This is the
		interface for setting a key throughout the network

		Parameters
		----------
			key: Union[bytes, str]
				ID of the resource to be stored
			value: Any
				Payload of the resource to be stored

		Returns
		-------
			asyncio.Future:
				Callback to set_digest which finds nodes on which to store key
		"""
		if not check_dht_value_type(value):
			raise TypeError("Value must be of type int, float, bool, str, or bytes")
		log.info("setting '%s' = '%s' on network", key, value)
		dkey = digest(key)
		return await self.set_digest(dkey, value)

	async def set_digest(self, dkey: bytes, value: Any) -> bool:
		"""
		Set the given SHA1 digest key (bytes) to the given value in the
		network.

		Parameters
		----------
			dkey: bytes
				ID of reosurce to be stored
			value: Any
				Payload of resource to be stored

		Returns
		-------
			bool:
				Indicator of whether or not the key/value pair was stored
				on any of the nearest nodes found by the SpiderCrawler
		"""
		node = Node(dkey)

		nearest = self.protocol.router.find_neighbors(node)
		if not nearest:
			log.warning("There are no known neighbors to set key %s", dkey.hex())
			return False

		spider = NodeSpiderCrawl(self.protocol, node, nearest, self.ksize, self.alpha)
		nodes = await spider.find()
		log.info("setting '%s' on %s", dkey.hex(), list(map(str, nodes)))

		# if this node is close too, then store here as well
		biggest = max([n.distance_to(node) for n in nodes])
		if self.node.distance_to(node) < biggest:
			self.storage[dkey] = value
		results = [self.protocol.call_store(n, dkey, value) for n in nodes]
		# return true only if at least one store call succeeded
		return any(await asyncio.gather(*results))

	def save_state(self, fname: str) -> None:
		"""
		Save the state of this node (the alpha/ksize/id/immediate neighbors)
		to a cache file with the given fname.

		Parameters
		----------
			fname: str
				File location where in which to write state

		Returns
		-------
			None
		"""
		log.info("Saving state to %s", fname)
		# pylint: disable=bad-continuation
		data = {
			'ksize': self.ksize,
			'alpha': self.alpha,
			'id': self.node.id,
			'neighbors': self.bootstrappable_neighbors()
		}
		if not data['neighbors']:
			log.warning("No known neighbors, so not writing to cache.")
			return
		with open(fname, 'wb') as file:
			pickle.dump(data, file)

	@classmethod
	def load_state(cls, fname: str) -> "Server":
		"""
		Load the state of this node (the alpha/ksize/id/immediate neighbors)
		from a cache file with the given fname.

		Parameters
		----------
			fname: str
				File location where in which to write state

		Returns
		-------
			Server:
				Parameterized instance of a Server
		"""
		log.info("Loading state from %s", fname)
		with open(fname, 'rb') as file:
			data = pickle.load(file)
		svr = Server(data['ksize'], data['alpha'], data['id'])
		if data['neighbors']:
			svr.bootstrap(data['neighbors'])
		return svr

	def save_state_regularly(self, fname: str, frequency: int = 600) -> None:
		"""
		Save the state of node with a given regularity to the given
		filename.

		Parameters
		----------
			fname: str
				File name to save retularly to
			frequency: int
				Frequency in seconds that the state should be saved. (default=10 mins)

		Returns
		-------
			None
		"""
		self.save_state(fname)
		loop = asyncio.get_event_loop()
		# pylint: disable=bad-continuation
		self.save_state_loop = loop.call_later(frequency,
												self.save_state_regularly,
												fname,
												frequency)


def check_dht_value_type(value: Any) -> bool:
	"""
	Checks to see if the type of the value is a valid type for
	placing in the dht.

	Parameters
	----------
		value: Any
			Value to be checked

	Returns
	-------
		bool:
			Indicating whether or not type is in DHT types
	"""
	# pylint: disable=bad-continuation
	typeset = [
		int,
		float,
		bool,
		str,
		bytes
	]
	return type(value) in typeset  # pylint: disable=unidiomatic-typecheck
