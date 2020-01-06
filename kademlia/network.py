import asyncio
import logging
import os
import pickle
from typing import List, Optional, Tuple

from kademlia.crawling import NodeSpiderCrawl, ValueSpiderCrawl
from kademlia.node import Node, NodeType
from kademlia.protocol import KademliaProtocol, HttpInterface
from kademlia.storage import StorageIface
from kademlia.utils import int_to_digest, rand_digest_id

log = logging.getLogger(__name__)  # pylint: disable=invalid-name


# pylint: disable=too-many-instance-attributes
class Server:

	protocol_class = KademliaProtocol

	# pylint: disable=bad-continuation
	def __init__(self,
		node_id: Optional[bytes] = None, ksize: int = 20, alpha: int = 3, **kwargs):
		"""
		High level view of a node instance.  This is the object that should be
		created to start listening as an active node on the network.
		Create a server instance.  This will start listening on the given port.

		Parameters
		----------
			node_id: Optional[bytes]
				The id for this node on the network.
			ksize: int
				The k parameter from the paper (default = 20)
			alpha: int
				The alpha parameter from the paper (default = 3)
		"""
		self.node = Node(node_id if node_id else rand_digest_id())
		log.info("Using storage interface: %s", StorageIface.__name__)
		self.storage = StorageIface(self.node)
		self.ksize = ksize
		self.alpha = alpha
		self.refresh_intv = kwargs.get("refresh_intv")
		self.statefile = os.path.join(self.storage.dir, "state.dat")

		self.udp_transport = None
		self.protocol = None
		self.refresh_loop = None
		self.save_state_loop = None
		self.listener = None

	def stop(self) -> None:
		"""
		Stop a currently running server - all event loops, and close
		all open network connections
		"""
		if self.udp_transport is not None:
			log.info("Closing %s udp transport...", self.node)
			self.udp_transport.close()

		if self.refresh_loop:
			log.info("Cancelling %s refresh loop...", self.node)
			self.refresh_loop.cancel()

		if self.save_state_loop:
			log.info("Cancelling %s state loop...", self.node)
			self.save_state_loop.cancel()

		if self.listener:
			log.info("Closing %s server...", self.node)
			asyncio.ensure_future(self.listener.wait_closed())

	def _create_protocol(self) -> "KademliaProtocol":
		"""
		Create an instance of the Kademlia protocol

		Returns
		-------
			KademliaProtocol:
				Instance of the kademlia protocol
		"""
		return self.protocol_class(self.node, self.storage, self.ksize)

	def _create_http_iface(self) -> "HttpInterface":
		return HttpInterface(self.node, self.storage)

	async def listen_udp(self, port: int, interface: str = "0.0.0.0") -> None:
		"""
		Start our datagram endpoint listening on the given port
		Provide interface="::" to accept ipv6 address

		Parameters
		----------
			port: int
				Port on which to listen
			interface: str
				Interface on which to bind port (deafult = 0.0.0.0)
		"""
		loop = asyncio.get_event_loop()
		# pylint: disable=bad-continuation
		listen = loop.create_datagram_endpoint(self._create_protocol,
												local_addr=(interface, port))

		self.node.ip = interface
		self.node.port = port
		log.info("%s UDP listening at %s:%i", self.node, interface, port)
		self.udp_transport, self.protocol = await listen
		# finally, schedule refreshing table
		self.refresh_table()

	async def listen_http(self, port: int, interface: str = "0.0.0.0") -> None:
		"""
		Start our http endpoint listening on the given port
		Provide interface="::" to accept ipv6 address

		Parameters
		----------
			port: int
				Port on which to listen
			interface: str
				Interface on which to bind port (deafult = 0.0.0.0)
		"""
		# if we are only using the http endpoint (and not the udp endpoint)
		if not self.node.port:
			self.node.port = port
		if not self.node.ip:
			self.node.ip = interface

		loop = asyncio.get_event_loop()
		# pylint: disable=bad-continuation
		self.listener = await loop.create_server(self._create_http_iface,
													host=interface, port=port)
		log.info("%s HTTP listening at %s:%i", self.node, interface, port)

		asyncio.ensure_future(self.listener.serve_forever())

	def refresh_table(self) -> None:
		"""
		Refresh our routing table and save our server's state
		"""
		interval = self.refresh_intv or 3600
		log.debug("Refreshing routing table for %s", self.node)
		asyncio.ensure_future(self._refresh_table())
		loop = asyncio.get_event_loop()
		self.refresh_loop = loop.call_later(interval, self.refresh_table)
		self.save_state_loop = loop.call_later(interval, self.save_state_regularly)

	async def _refresh_table(self) -> None:
		"""
		Refresh buckets that haven't had any lookups in the last hour
		(per section 2.3 of the paper).
		"""
		results: List[asyncio.Future] = []
		for digest_id in self.protocol.get_refresh_ids():
			node = Node(digest_id)
			nearest = self.protocol.router.find_neighbors(node, self.alpha)
			log.debug("%s refreshing routing table on %i nearest", self.node, len(nearest))
			spider = NodeSpiderCrawl(self.protocol, node, nearest, self.ksize, self.alpha)
			results.append(spider.find())

		# do our crawling
		await asyncio.gather(*results)

		# now republish keys older than one hour
		for node in self.storage.iter_older_than(3600):
			# node = Node(hex_to_int_digest(hexkey), type=NodeType.Resource, value=value)
			log.debug("%s republishing node %s from store", self.node, node)
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

	async def bootstrap(self, addrs: List[Tuple[str, int]]) -> asyncio.Future:
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
		log.debug("%s attempting to bootstrap with contacts: %s", self.node, addrs)
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

	async def get(self, key: int) -> asyncio.Future:
		"""
		Crawl the current node's known network in order to find a given key. This
		is the interface for grabbing a key from the network

		Parameters
		----------
			key: int
				Key to find in network

		Returns
		-------
			asyncio.Future:
				A recursive call to ValueSpiderCrawl.find which will terminate
				either when the value is find or the search is exhausted
		"""
		log.info("%s looking up key %s", self.node, key)
		dkey = int_to_digest(key)

		# if this node has it, return it
		result = self.storage.get(dkey.hex())
		if result is not None:
			return result

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
		log.info("setting '%s' on %s", str(node), ",".join(list(map(str, nodes))))

		# if this node is close too, then store here as well
		biggest = max([n.distance_to(node) for n in nodes])
		if self.node.distance_to(node) < biggest:
			self.storage.set(node)
		results = [self.protocol.call_store(n, node.digest_id, node.value) for n in nodes]
		# return true only if at least one store call succeeded
		return any(await asyncio.gather(*results))

	def save_state(self, fname: Optional[str] = None) -> None:
		"""
		Save the state of this node (the alpha/ksize/id/immediate neighbors)
		to a cache file with the given fname.

		Parameters
		----------
			fname: strtest_can_set_and_get
				File location where in which to write state
		"""
		fname = fname or self.statefile
		log.info("%s saving state to %s", self.node, fname)
		# pylint: disable=bad-continuation
		data = {
			'ksize': self.ksize,
			'alpha': self.alpha,
			'id': self.node.digest_id,
			'neighbors': self.bootstrappable_neighbors()
		}
		if not data['neighbors']:
			log.warning("%s has no known neighbors, so not writing to cache.", self.node)
			return
		with open(fname, 'wb') as file:
			pickle.dump(data, file)

	def load_state(self, fname: Optional[str] = None) -> "Server":
		"""
		Load the state of this node (the alpha/ksize/id/immediate neighbors)
		from a cache file with the given fname.

		Parameters
		----------
			fname: Optional[str]
				File location where in which to write state
					(default is state.dat file in storage directory)

		Returns
		-------
			Server:
				Parameterized instance of a Server
		"""
		fname = fname or self.statefile
		log.info("%i loading state from %s", self.node, fname)
		with open(fname, 'rb') as file:
			data = pickle.load(file)
		svr = Server(data['id'], ksize=data['ksize'], alpha=data['alpha'])
		if data['neighbors']:
			asyncio.ensure_future(svr.bootstrap(data['neighbors']))
		return svr

	# pylint: disable=bad-continuation
	def save_state_regularly(self,
		fname: Optional[str] = None,
		frequency: int = 600
	) -> None:
		"""
		Save the state of node with a given regularity to the given
		filename.

		Parameters
		----------
			fname: Optional[str]
				Location at which to save state regularly
					(default is state.dat file in storage directory)
			frequency: int
				Frequency in seconds that the state should be saved. (default=10 mins)
		"""
		fname = fname or self.statefile
		self.save_state(fname)
		loop = asyncio.get_event_loop()
		# pylint: disable=bad-continuation
		self.save_state_loop = loop.call_later(frequency,
												self.save_state_regularly,
												fname,
												frequency)
