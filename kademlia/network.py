import pickle
import asyncio
import logging
from typing import List, Tuple, Union, Optional

from kademlia.protocol import KademliaProtocol
from kademlia.utils import digest, rand_digest_id
from kademlia.storage import EphemeralStorage
from kademlia.node import Node, NodeType
from kademlia.crawling import ValueSpiderCrawl, NodeSpiderCrawl
from kademlia.config import CONFIG


log = logging.getLogger(__name__)  # pylint: disable=invalid-name


# pylint: disable=too-many-instance-attributes
class Server:

	protocol_class = KademliaProtocol

	# pylint: disable=bad-continuation
	def __init__(self,
			ksize: int = CONFIG.ksize,
			alpha: int = CONFIG.alpha,
			node_id: Optional[int] = None,
			storage: Optional["EphemeralStorage"] = None
	):
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
			node_id: Optional[int]
				The id for this node on the network.
			storage: Optional[EphemeralStorage]
				A storage interface
		"""
		self.ksize = ksize
		self.alpha = alpha
		self.storage = storage or EphemeralStorage()
		self.node = Node(node_id or rand_digest_id())
		self.transport = None
		self.protocol = None
		self.refresh_loop = None
		self.save_state_loop = None

	def stop(self) -> None:
		"""
		Stop a currently running server - all event loops, and close
		all open network connections
		"""
		if self.transport is not None:
			self.transport.close()

		if self.refresh_loop:
			self.refresh_loop.cancel()

		if self.save_state_loop:
			self.save_state_loop.cancel()

	def _create_protocol(self) -> "KademliaProtocol":
		"""
		Create an instance of the Kademlia protocol

		Returns
		-------
			KademliaProtocol:
				Instance of the kademlia protocol
		"""
		return self.protocol_class(self.node, self.storage, self.ksize)

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
		"""
		loop = asyncio.get_event_loop()
		# pylint: disable=bad-continuation
		listen = loop.create_datagram_endpoint(self._create_protocol,
															local_addr=(interface, port))

		self.node.ip = interface
		self.node.port = port
		log.info("Node %s listening at %s:%i", self.node, interface, port)
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
		"""
		log.debug("Refreshing routing table for %s", self.node)
		asyncio.ensure_future(self._refresh_table())
		loop = asyncio.get_event_loop()
		self.refresh_loop = loop.call_later(delay, self.refresh_table)

	async def _refresh_table(self) -> None:
		"""
		Refresh buckets that haven't had any lookups in the last hour
		(per section 2.3 of the paper).
		"""
		results: List[asyncio.Future] = []
		for digest_id in self.protocol.get_refresh_ids():
			node = Node(digest_id)
			nearest = self.protocol.router.find_neighbors(node, self.alpha)
			log.debug("Node %s refreshing routing table on %i nearest", self.node, len(nearest))
			spider = NodeSpiderCrawl(self.protocol, node, nearest, self.ksize, self.alpha)
			results.append(spider.find())

		# do our crawling
		await asyncio.gather(*results)

		# now republish keys older than one hour
		for dkey, value in self.storage.iter_older_than(3600):
			node = Node(dkey, type=NodeType.Resource, value=value)
			log.debug("Node %s republishing resource node %i", self.node, str(node))
			await self.set_digest(node)

	def bootstrappable_neighbors(self) -> List["Node"]:
		"""
		Get a list of (ip, port) tuple pairs suitable for use as an argument to
		the bootstrap method.

		The server should have been bootstrapped
		already - this is just a utility for getting some neighbors and then
		storing them if this server is going down for a while.  When it comes
		back up, the list of nodes can be used to bootstrap.

		Returns
		-------
			List[Node]:
				List of peers suitable for bootstrap use
		"""
		neighbors: List["Node"] = self.protocol.router.find_neighbors(self.node)
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
		log.debug("Node %s attempting to bootstrap node with %i initial contacts", self.node, len(addrs))
		cos = list(map(self.bootstrap_node, addrs))
		gathered = await asyncio.gather(*cos)
		nodes = [node for node in gathered if node is not None]
		spider = NodeSpiderCrawl(self.protocol, self.node, nodes, self.ksize, self.alpha)
		return await spider.find()

	async def bootstrap_node(self, addr: Tuple[str, int]) -> Optional["Node"]:
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
		result = await self.protocol.ping(addr, self.node.digest_id)
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
		log.info("Node %s looking up key %s", self.node, key)
		dkey = digest(key)
		# if this node has it, return it
		if self.storage.get(dkey) is not None:
			return self.storage[dkey]
		node = Node(dkey, type=NodeType.Resource)
		nearest = self.protocol.router.find_neighbors(node)
		if not nearest:
			log.warning("There are no known neighbors to get key %s", str(node))
			return None
		spider = ValueSpiderCrawl(self.protocol, node, nearest, self.ksize, self.alpha)
		return await spider.find()

	async def set(self, node: "Node") -> asyncio.Future:
		"""
		Set the given string key to the given value in the network. This is the
		interface for setting a key throughout the network

		Parameters
		----------
			node: Node
				Node to be stored

		Returns
		-------
			asyncio.Future:
				Callback to set_digest which finds nodes on which to store key
		"""
		if not node.has_valid_value():
			raise TypeError("Value must be of type int, float, bool, str, or bytes")
		log.info("setting '%s' = '%s' on network", str(node), node.value)
		return await self.set_digest(node)

	async def set_digest(self, node: "Node") -> bool:
		"""
		Set the given SHA1 digest key (bytes) to the given value in the
		network.

		Parameters
		----------
			node: Node
				Node to be set (where node.type == NodeType.Resource)

		Returns
		-------
			bool:
				Indicator of whether or not the key/value pair was stored
				on any of the nearest nodes found by the SpiderCrawler
		"""
		nearest = self.protocol.router.find_neighbors(node)
		if not nearest:
			log.warning("There are no known neighbors to set key %s", node.hex)
			return False

		spider = NodeSpiderCrawl(self.protocol, node, nearest, self.ksize, self.alpha)
		nodes = await spider.find()
		log.info("setting '%s' on %s", str(node), list(map(str, nodes)))

		# if this node is close too, then store here as well
		biggest = max([n.distance_to(node) for n in nodes])
		if self.node.distance_to(node) < biggest:
			self.storage[node.digest_id] = node.value
		results = [self.protocol.call_store(n, node.digest_id, node.value) for n in nodes]
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
		"""
		log.info("%i saving state to %s", self.node, fname)
		# pylint: disable=bad-continuation
		data = {
			'ksize': self.ksize,
			'alpha': self.alpha,
			'id': self.node.digest_id,
			'neighbors': self.bootstrappable_neighbors()
		}
		if not data['neighbors']:
			log.warning("Node %s has no known neighbors, so not writing to cache.", self.node)
			return
		with open(fname, 'wb') as file:
			pickle.dump(data, file)

	def load_state(self, fname: str) -> "Server":
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
		log.info("%i loading state from %s", self.node, fname)
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
		"""
		self.save_state(fname)
		loop = asyncio.get_event_loop()
		# pylint: disable=bad-continuation
		self.save_state_loop = loop.call_later(frequency,
												self.save_state_regularly,
												fname,
												frequency)
