import asyncio
import logging
import os
import pickle

from liaa import __version__
from liaa.crawler import NodeSpiderCrawl, ValueSpiderCrawl
from liaa.node import Node, PeerNode, ResourceNode
from liaa.protocol import KademliaProtocol, HttpInterface
from liaa.storage import StorageIface
from liaa.utils import join_addr

log = logging.getLogger(__name__)  # pylint: disable=invalid-name


# pylint: disable=too-many-instance-attributes
class Server:

	protocol_class = KademliaProtocol

	def __init__(self, interface, port, ksize=20, alpha=3, **kwargs):
		"""
		High level view of a node instance.  This is the object that should be
		created to start listening as an active node on the network.
		Create a server instance.  This will start listening on the given port.

		Parameters
		----------
			interface: str
				Interface on which to listen (default = 0.0.0.0)
			port: int
				Port on which to bind inteface
			ksize: int
				The k parameter from the paper (default = 20)
			alpha: int
				The alpha parameter from the paper (default = 3)
		"""
		self.node = PeerNode(key=join_addr((interface, port)))
		log.info("Using storage interface: %s", StorageIface.__name__)
		self.storage = StorageIface(self.node)
		self.ksize = ksize
		self.alpha = alpha
		self.refresh_interval = kwargs.get("refresh_interval")
		self.statefile = os.path.join(self.storage.dir, "node.state")

		self.udp_transport = None
		self.protocol = None
		self.refresh_loop = None
		self.save_state_loop = None
		self.listener = None

		self._ssl_ctx = None

	@property
	def ssl_ctx(self):
		"""
		Returns
		-------
			ssl.SSLContext
		"""
		return self._ssl_ctx

	@ssl_ctx.setter
	def ssl_ctx(self, ctx):
		"""
		Parameters
		----------
			ctx: Optional[ssl.SSLContext]
		"""
		if not ctx:
			log.warning(
				"%s ssl context being set to none. http traffic not encrypted",
				self.node,
			)
		self._ssl_ctx = ctx

	def stop(self):
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

	def _create_protocol(self):
		"""
		Create an instance of the Kademlia protocol

		Returns
		-------
			KademliaProtocol:
				Instance of the kademlia protocol
		"""
		return self.protocol_class(self.node, self.storage, self.ksize)

	def _create_http_iface(self):
		"""
		Create an interface to accept incoming http messages

		Returns
		-------
			HttpInterface:
				Bootstrapped instance of an HttpInterface
		"""
		return HttpInterface(self.node, self.storage)

	async def listen(self):
		"""
		Create UDP and HTTP listeners on the server
		"""
		loop = asyncio.get_event_loop()
		# pylint: disable=bad-continuation
		listen = loop.create_datagram_endpoint(
			self._create_protocol, local_addr=(self.node.ip, self.node.port)
		)
		log.info("%s udp listening at udp://%s", self.node, self.node.key)

		self.udp_transport, self.protocol = await listen

		# schedule refreshing table
		self.refresh_table()

		# pylint: disable=bad-continuation
		self.listener = await loop.create_server(
			self._create_http_iface,
			host=self.node.ip,
			port=self.node.port,
			ssl=self._ssl_ctx,
		)
		log.info("%s https listening at https://%s", self.node, self.node.key)

		asyncio.ensure_future(self.listener.serve_forever())

	def refresh_table(self):
		"""
		Refresh our routing table and save our server's state
		"""
		interval = self.refresh_interval or 10
		log.debug("Refreshing routing table for %s", self.node)
		asyncio.ensure_future(self._refresh_table())
		loop = asyncio.get_event_loop()
		self.refresh_loop = loop.call_later(interval, self.refresh_table)
		self.save_state_loop = loop.call_later(interval, self.save_state_regularly)

	async def _refresh_table(self):
		"""
		Section 2.3

		Refresh buckets that haven't had any lookups in the last hour
		"""
		results = []
		for key in self.protocol.get_refresh_ids():
			node = Node(key=key)
			nearest = self.protocol.router.find_neighbors(node, self.alpha)
			log.debug(
				"%s refreshing routing table on %i nearest", self.node, len(nearest)
			)
			spider = NodeSpiderCrawl(
				self.protocol, node, nearest, self.ksize, self.alpha
			)
			results.append(spider.find())

		await asyncio.gather(*results)

		for data in self.storage.iter_older_than(20):
			node = ResourceNode(*data)
			log.debug("%s republishing node %s from store", self.node, node)
			await self.set_digest(node)

	def bootstrappable_neighbors(self):
		"""
		Get a list of (ip, port) tuple pairs suitable for use as an argument to
		the bootstrap method.

		The server should have been bootstrapped
		already - this is just a utility for getting some neighbors and then
		storing them if this server is going down for a while.  When it comes
		back up, the list of nodes can be used to bootstrap.

		Returns
		-------
			List[PeerNode]:
				List of peers suitable for bootstrap use
		"""
		neighbors = self.protocol.router.find_neighbors(self.node)
		return [tuple(n)[-2:] for n in neighbors]

	async def bootstrap(self, addrs):
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
				scheduled callback for a NodeSpiderCrawl to continue crawler
				network in order to find peers for self.node
		"""
		log.debug("%s attempting to bootstrap with contacts: %s", self.node, addrs)
		cos = list(map(self.bootstrap_node, addrs))
		gathered = await asyncio.gather(*cos)
		nodes = [node for node in gathered if node is not None]
		spider = NodeSpiderCrawl(
			self.protocol, self.node, nodes, self.ksize, self.alpha
		)
		return await spider.find()

	async def bootstrap_node(self, addr):
		"""
		Ping a given address so that both `addr` and `self.node` can know
		about one another

		Parameters
		----------
			addr: Tuple[str, int]
				Address of peer to ping

		Returns
		-------
			Optiona[PeerNode]:
				None if ping was unsuccessful, or peer as Node if ping
				was successful
		"""
		result = await self.protocol.ping(addr, self.node.key)
		return PeerNode(key=join_addr((addr[0], addr[1]))) if result[0] else None

	async def get(self, key):
		"""
		Crawl the current node's known network in order to find a given key. This
		is the interface for grabbing a key from the network

		Parameters
		----------
			key: str
				Key to find in network

		Returns
		-------
			asyncio.Future:
				A recursive call to ValueSpiderCrawl.find which will terminate
				either when the value is find or the search is exhausted
		"""
		log.info("%s looking up key %s", self.node, key)

		# if this node has it, return it
		result = self.storage.get(key)
		if result is not None:
			return result

		node = ResourceNode(key, value=None)
		nearest = self.protocol.router.find_neighbors(node)

		if not nearest:
			log.warning("There are no known neighbors to get key %s", node.key)
			return None

		spider = ValueSpiderCrawl(self.protocol, node, nearest, self.ksize, self.alpha)
		return await spider.find()

	async def set(self, node):
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
			log.error("Value must be of type int, float, bool, str, or bytes")
		log.info("%s setting %s on network", str(self.node), str(node))
		return await self.set_digest(node)

	async def set_digest(self, node):
		"""
		Set the given SHA1 digest key (bytes) to the given value in the
		network.

		Parameters
		----------
			node: Node
				Node to be set (where node.node_type == 'resource')

		Returns
		-------
			bool:
				Indicator of whether or not the key/value pair was stored
				on any of the nearest nodes found by the SpiderCrawler
		"""
		nearest = self.protocol.router.find_neighbors(node)
		if not nearest:
			log.warning("There are no known neighbors to set key %s", node.key)
			return False

		spider = NodeSpiderCrawl(self.protocol, node, nearest, self.ksize, self.alpha)
		nodes = await spider.find()
		log.info("setting '%s' on %s", str(node), ",".join(list(map(str, nodes))))

		# if this node is close too, then store here as well
		biggest = max([n.distance_to(node) for n in nodes])
		if self.node.distance_to(node) < biggest:
			self.storage.set(node)
		results = [self.protocol.call_store(n, node.key, node.value) for n in nodes]

		# return true only if at least one store call succeeded
		return any(await asyncio.gather(*results))

	def save_state(self, fname=None):
		"""
		Save the state of this node (the alpha/ksize/id/immediate neighbors)
		to a cache file with the given fname.

		Parameters
		----------
			fname: Optional[str]
				File location where in which to write state
		"""
		fname = fname or self.statefile
		log.info("%s saving state to %s", self.node, fname)

		# pylint: disable=bad-continuation
		data = {
			"interface": self.node.ip,
			"port": self.node.port,
			"ksize": self.ksize,
			"alpha": self.alpha,
			"id": self.node.key,
			"neighbors": self.bootstrappable_neighbors(),
		}

		if not data["neighbors"]:
			log.warning(
				"%s has no known neighbors, so not writing to cache.", self.node
			)
			return

		with open(fname, "wb") as file:
			pickle.dump(data, file)

	def load_state(self, fname=None):
		"""
		Load the state of this node (the alpha/ksize/id/immediate neighbors)
		from a cache file with the given fname.

		Parameters
		----------
			fname: Optional[str]
				File location where in which to write state
					(default is node.state file in storage directory)

		Returns
		-------
			Server:
				Parameterized instance of a Server
		"""
		fname = fname or self.statefile
		log.info("%i loading state from %s", self.node, fname)

		with open(fname, "rb") as file:
			data = pickle.load(file)

		svr = Server(
			data["interface"], data["port"], ksize=data["ksize"], alpha=data["alpha"]
		)

		if data["neighbors"]:
			asyncio.ensure_future(svr.bootstrap(data["neighbors"]))

		return svr

	def save_state_regularly(self, fname=None, frequency=600):
		"""
		Save the state of node with a given regularity to the given
		filename.

		Parameters
		----------
			fname: Optional[str]
				Location at which to save state regularly
					(default is node.state file in storage directory)
			frequency: int
				Frequency in seconds that the state should be saved. (default=10 mins)
		"""
		fname = fname or self.statefile
		self.save_state(fname)
		loop = asyncio.get_event_loop()

		# pylint: disable=bad-continuation
		self.save_state_loop = loop.call_later(
			frequency, self.save_state_regularly, fname, frequency
		)
