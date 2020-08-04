import asyncio
import logging
import os
import pickle

from _typing import *

from liaa import __version__
from liaa.crawler import NodeSpiderCrawl, ValueSpiderCrawl
from liaa.node import GenericNode, PingNode, IndexNode
from liaa.protocol import KademliaProtocol
from liaa.storage import EphemeralStorage
from liaa.utils import join_addr

log = logging.getLogger(__name__)


# pylint: disable=too-many-instance-attributes
class Server:

    protocol_class = KademliaProtocol

    def __init__(self, interface: str, port: int, ksize: int = 20, alpha: int = 3, **kwargs: str):
        """
        @description
            High level view of a node instance.  This is the object that should be
            created to start listening as an active node on the network.
            Create a server instance.  This will start listening on the given port.

		@parameters
            interface: str
				Interface on which to listen (default = 0.0.0.0)
			port: int
				Port on which to bind inteface
			ksize: int
				The k parameter from the paper (default = 20)
			alpha: int
				The alpha parameter from the paper (default = 3)
		"""
        self.node = PingNode(key=join_addr((interface, port)))
        self.storage = EphemeralStorage(self.node)
        self.ksize = ksize
        self.alpha = alpha
        self.refresh_loop: AsyncioLoop
        self.refresh_interval: int = int(kwargs.get("refresh_interval", "10"))
        self.save_state_loop: AsyncioLoop
        self.state_filepath: str = os.path.join(self.storage.dir, "node.state")
        self.transport: UDPTransport
        self.protocol: KademliaProtocol
       
    def stop(self) -> None:
        """
        @description
            Stop a currently running server - all event loops, and close
            all open network connections
		"""
        if self.transport is not None:
            log.info("Closing %s udp transport...", self.node)
            self.transport.close()

        if self.refresh_loop:
            log.info("Cancelling %s refresh loop...", self.node)
            self.refresh_loop.cancel()

        if self.save_state_loop:
            log.info("Cancelling %s state loop...", self.node)
            self.save_state_loop.cancel()

    def _create_protocol(self) -> BaseProtocol:
        return KademliaProtocol(self.node, self.storage, self.ksize)

    async def listen(self) -> None:
        """
		@description
            Create UDP and HTTP listeners on the server
		"""
        loop = asyncio.get_event_loop()
        listen = loop.create_datagram_endpoint(self._create_protocol, local_addr=self.node.addr())
        log.info("%s udp listening at udp://%s", self.node, self.node.key)

        self.transport, self.protocol = await listen  # type: ignore

        self.refresh_table()


    def refresh_table(self) -> None:
        """
        @descriptoin
		    Refresh our routing table and save our server's state
		"""
        log.debug("Refreshing routing table for %s", self.node)
        asyncio.ensure_future(self._refresh_table())
        loop = asyncio.get_event_loop()
        self.refresh_loop = loop.call_later(self.refresh_interval, self.refresh_table)
        self.save_state_loop = loop.call_later(self.refresh_interval, self.save_state_regularly)

    async def _refresh_table(self) -> None:
        """
        @description
            Section 2.3

            Refresh buckets that haven't had any lookups in the last hour
		"""
        results = []
        for key in self.protocol.get_refresh_ids():
            node = PingNode(key)
            nearest = self.protocol.router.find_neighbors(node, self.alpha)
            log.debug(
                "%s refreshing routing table on %i nearest", self.node, len(nearest)
            )
            spider = NodeSpiderCrawl(
                self.protocol, node, nearest, self.ksize, self.alpha
            )
            results.append(spider.find())

        await asyncio.gather(*results)

        for node in self.storage.iter_older_than(20):
            log.debug("%s republishing node %s from store", self.node, node)
            _ = await self.set_digest(node)

    def bootstrappable_neighbors(self) -> List[IPv4]:
        """
        @description
            Get a list of (ip, port) tuple pairs suitable for use as an argument to
            the bootstrap method.

            The server should have been bootstrapped
            already - this is just a utility for getting some neighbors and then
            storing them if this server is going down for a while.  When it comes
            back up, the list of nodes can be used to bootstrap.

		@returns
            List[IPv4]
				List of peers suitable for bootstrap use
		"""
        neighbors = self.protocol.router.find_neighbors(self.node)
        return [tuple(n)[-2:] for n in neighbors]

    async def bootstrap(self, addrs: List[IPv4]) -> Optional[NodeSpiderFindReturn]:  # type: ignore
        """
        @description
		    Bootstrap the server by connecting to other known nodes in the network.

		@parameters
            addrs: List[IPv4]
				Note that only IP addresses are acceptable - hostnames will
				cause an error.

		@returns
            Optional[NodeSpiderFindReturn]:
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

    async def bootstrap_node(self, addr: IPv4) -> Optional[PingNode]:
        """
        @description
            Ping a given address so that both `addr` and `self.node` can know
            about one another

		@parameters
            addr: IPv4
				Address of peer to ping

		@returns
            Optiona[PingNode]
				None if ping was unsuccessful, or peer as Node if ping
				was successful
		"""
        result = await self.protocol.ping(addr, self.node.key)
        addr = join_addr((addr[0], addr[1]))
        return PingNode(key=addr) if result[0] else None
       


    async def get(self, key: str) -> Optional[ResponseIndex]:
        """
        @description
            Crawl the current node's known network in order to find a given key. This
            is the interface for grabbing a key from the network

		@parameters
            key: str
				Key to find in network

		@returns
            Optional[ResponseIndex]
				A recursive call to ValueSpiderCrawl.find which will terminate
				either when the value is find or the search is exhausted
		"""
        log.info("%s looking up key %s", self.node, key)

        result = self.storage.get(key)
        if result is not None:
            return result

        # we only use this node's key for distance, so it could possibly be a 
        # PingNode as well
        node = IndexNode(key, value=None)
        nearest = self.protocol.router.find_neighbors(node)

        if not nearest:
            log.warning("There are no known neighbors to get key %s", node.key)
            return None

        spider = ValueSpiderCrawl(self.protocol, node, nearest, self.ksize, self.alpha)
        return await spider.find()

    async def set(self, node: IndexNode) -> Optional[bool]:
        """
        @description
            Set the given string key to the given value in the network. This is the
            interface for setting a key throughout the network

		@parameters
            node: IndexNode
				Node to be stored

		@returns
            Optional[bool]
				Indicator of whether or not the operation succeeded
		"""
        if not node.has_valid_value():
            log.error("Value must be of type int, float, bool, str, or bytes")
            return None
        log.info("%s setting %s on network", str(self.node), str(node))
        return await self.set_digest(node)

    async def set_digest(self, node: IndexNode) -> bool:
        """
        @description
            Set the given SHA1 digest key (bytes) to the given value in the
            network.

		@parameters
            node: IndexNode
				Node to be set

		@returns
            bool
				Indicator of whether or not the key/value pair was stored
				on any of the nearest nodes found by the SpiderCrawler
		"""
        nearest = self.protocol.router.find_neighbors(node)
        if not nearest:
            log.warning("There are no known neighbors to set key %s", node.key)
            return False

        # an IndexNode can be a PingNode but a PingNode can't be an IndexNode
        spider = NodeSpiderCrawl(self.protocol, node, nearest, self.ksize, self.alpha)
        nodes = await spider.find()

        index_nodes = [n for n in nodes if isinstance(n, IndexNode)]
        log.info("setting '%s' on %s", str(node), ",".join(list(map(str, index_nodes))))

        # if this node is close too, then store here as well
        biggest = max([n.distance_to(node) for n in index_nodes])
        if self.node.distance_to(node) < biggest:
            self.storage.set(node)
            
        results = [self.protocol.call_store(node, n) for n in nodes]

        # return true only if at least one store call succeeded
        return any(await asyncio.gather(*results))

    def save_state(self, fname: Optional[str] = None) -> None:
        """
        @description
            Save the state of this node (the alpha/ksize/id/immediate neighbors)
            to a cache file with the given fname.

		@parameters
            fname: Optional[str]
				Filesystem location at which to write state
		"""
        fname = fname or self.state_filepath
        log.info("%s saving state to %s", self.node, fname)

        ip, port = self.node.addr()
        data = {
            "interface": ip,
            "port": port,
            "ksize": self.ksize,
            "alpha": self.alpha,
            "id": self.node.key,
            "neighbors": self.bootstrappable_neighbors(),
        }

        if not data["neighbors"]:
            log.warning(
                "%s has no known neighbors, so not writing to cache.", self.node
            )
            return None

        with open(fname, "wb") as file:
            pickle.dump(data, file)

    def load_state(self, fname: Optional[str] = None) -> TServer:
        """
        @description
            Load the state of this node (the alpha/ksize/id/immediate neighbors)
            from a cache file with the given fname.

		@parameters
            fname: Optional[str]
				Filesystem location at which to write state

		@returns
            Server
				Parameterized instance of a Server
		"""
        fname = fname or self.state_filepath
        log.info("%i loading state from %s", self.node, fname)

        with open(fname, "rb") as file:
            data = pickle.load(file)

        svr = Server(
            data["interface"], data["port"], ksize=data["ksize"], alpha=data["alpha"]
        )

        if data["neighbors"]:
            asyncio.ensure_future(svr.bootstrap(data["neighbors"]))

        return svr

    def save_state_regularly(self, fname: Optional[str] = None, frequency: int = 600) -> None:
        """
        @description
            Save the state of node with a given regularity to the given
            filename.

		@parameters
			fname: Optional[str]
				Location at which to save state regularly
					(default is node.state file in storage directory)
			frequency: int
				Frequency in seconds that the state should be saved. (default=10 mins)
		"""
        fname = fname or self.state_filepath
        self.save_state(fname)
        loop = asyncio.get_event_loop()

        self.save_state_loop = loop.call_later(
            frequency, self.save_state_regularly, fname, frequency
        )
