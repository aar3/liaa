# multi_peer_simulator.py
#
# In this more complex example, we create num_peers peer nodes in a
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

from liaa.network import Server
from liaa.utils import rand_str, rand_digest_id
from liaa.node import Node, NodeType

# pylint: disable=invalid-name

host = "127.0.0.1"
num_peers = 20
start_port = 8000


handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
log = logging.getLogger('liaa')
log.addHandler(handler)
log.setLevel(logging.DEBUG)


async def make_fake_data(server):
	while True:
		resource = Node(rand_digest_id(), type=NodeType.Resource, value=rand_str())
		await server.set(resource)
		await asyncio.sleep(5)


def run_server(loop, server, port, neighbor_ports):
	"""
	Start a given server on a given port using a given event loop
	"""
	loop.set_debug(True)
	loop.run_until_complete(server.listen(port))

	bootstrap_peers = [(host, p) for p in neighbor_ports]
	loop.create_task(server.bootstrap(bootstrap_peers))
	loop.create_task(make_fake_data(server))
	loop.run_forever()


def main():

	handles = []
	servers = []

	for _ in range(num_peers):
		ksize = random.randint(14, 20)
		alpha = random.randint(2, 6)
		server = Server(ksize=ksize, alpha=alpha)
		servers.append(server)

	ports = range(start_port, (start_port + num_peers))

	for server, port in zip(servers, ports):
		boostrap_port_pool = [p for p in ports if p != port]
		loop = asyncio.new_event_loop()
		neighbor_ports = random.sample(boostrap_port_pool, random.randint(1, 3))
		handle = threading.Thread(target=run_server, args=(loop, server, port, neighbor_ports))
		handle.start()

	for handle in handles:
		handle.join()


if __name__ == "__main__":

	main()
