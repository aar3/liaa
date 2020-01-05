# multi_peer_simulator.py
#
# In this more complex example, we create NUM_PEERS peer nodes in a
# virtual network, using a separate thread for each peer's operations (listening,
# boostrapping, creating resources, etc). In this thread we simply instantiate
# a peer's listener, bootstrap the peer, then, similar to examples/multi_peer_set.py,
# we start creating random resources and setting them throughout the network.
#
# The idea here is that as opposed to creating peer's in different terminal tabs,
# we can create as many peer's as we want, with each peer generating its own
# resources, and interacting with the network autonomously, so that we can ensure
# that the network works as expected, at scale
#
# Example
# -------
# python examples/multi_peer_simulator.py

import logging
import asyncio
import random
import threading

from kademlia.network import Server
from kademlia.utils import rand_str, rand_digest_id
from kademlia.node import Node, NodeType


HOST = "127.0.0.1"
NUM_PEERS = 5
START_PORT = 8000
SLEEP = random.randint(2, 5)

def run_server(loop, server, port, bootstrap_port):
	"""
	Start a given server on a given port using a given event loop
	"""
	loop.set_debug(True)
	loop.run_until_complete(server.listen_udp(port))

	loop.run_until_complete(server.bootstrap([(HOST, bootstrap_port)]))

	while True:

		resource = Node(rand_digest_id(), type=NodeType.Resource, value=rand_str())
		loop.run_until_complete(server.set(resource))
		loop.run_until_complete(asyncio.sleep(SLEEP))


def main():

	handler = logging.StreamHandler()
	formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	handler.setFormatter(formatter)
	log = logging.getLogger('kademlia')
	log.addHandler(handler)
	log.setLevel(logging.DEBUG)

	handles = []
	servers = [Server() for _ in range(NUM_PEERS)]
	ports = range(START_PORT, (START_PORT + NUM_PEERS))
	for server, port in zip(servers, ports):

		boostrap_port_pool = [p for p in ports if p != port]
		loop = asyncio.new_event_loop()
		bootstrap_port = random.choice(boostrap_port_pool)
		handle = threading.Thread(target=run_server, args=(loop, server, port, bootstrap_port))
		handle.start()

	for handle in handles:
		handle.join()


if __name__ == "__main__":

	main()
