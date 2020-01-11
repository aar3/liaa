# multi_peer_set.py
#
# In this example, we merely instantiate a single peer using a given port, and
# boostrap peer address (provided via command line args) and run a loop that
# creates a random resource and sets it on this peer's server.
#
# The idea is that we open a few terminal tabs, and run this program using a few
# different ports, in order to ensure that the network is behaving as expected
#
# Example
# -------
# 	In terminal tab #1
# 		- python examples/simple_peer.py -p 8000
#
# 	In terminal tab #2
# 		- python examples/multi_peer_set.py -p 8001 -n 127.0.0.1:8000
#
# 	In terminal tab #3
# 		- python examples/multi_peer_set.py -p 8002 -n 127.0.0.1:8001

import logging
import asyncio
import time
import sys
import getopt

from liaa.network import Server
from liaa.node import Node, NodeType
from liaa.utils import rand_str, split_addr, ArgsParser, rand_digest_id, str_arg_to_bool


def usage():
	return """
Usage: python multi_peer_set.py -p [port] -n [bootstrap neighbors]
-p --port
	Port on which to listen (e.g., 8000)
-n --neighbors
	Neighbors with which to bootstrap (e.g., 177.91.19.1:8000,178.31.13.21:9876)
		or 'False' if not passing an args
	"""

async def make_fake_data(server):
	while True:
		resource = Node(rand_digest_id(), node_type=NodeType.Resource, value=rand_str())
		await server.set(resource)
		await asyncio.sleep(5)


def main():

	handler = logging.StreamHandler()
	formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	handler.setFormatter(formatter)
	log = logging.getLogger('liaa')
	log.addHandler(handler)
	log.setLevel(logging.DEBUG)

	loop = asyncio.get_event_loop()

	server = Server()

	parser = ArgsParser()

	try:
		args = "p:n:"
		long_args = ["--port", "--neighbors="]
		opts, args = getopt.getopt(sys.argv[1:], args, long_args)
		parser.add_many(opts)
	except getopt.GetoptError as err:
		log.error("GetoptError: %s", err)
		print(usage())
		sys.exit(1)

	if parser.has_help_opt() or not parser.has_proper_opts():
		print(usage())
		sys.exit(1)

	loop.run_until_complete(server.listen(int(parser.get("-p", "--port"))))

	bootstrap_peers = str_arg_to_bool(parser.get("-n", "--neighbors"))
	if bootstrap_peers:
		bootstrap_peers = bootstrap_peers.split(",")
		loop.run_until_complete(server.bootstrap(list(map(split_addr, bootstrap_peers))))

	try:
		loop.create_task(make_fake_data(server))
		loop.run_forever()
	except KeyboardInterrupt:
		log.info("Attempting to gracefully shut down...")
	finally:
		server.stop()
		log.info("Shutdown successul")

if __name__ == "__main__":

	main()
