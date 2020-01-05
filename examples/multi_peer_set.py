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
# 		- python examples/multi_peer_set.py -p 8001 -a 127.0.0.1:8000
#
# 	In terminal tab #3
# 		- python examples/multi_peer_set.py -p 8002 -a 127.0.0.1:8001

import logging
import asyncio
import sys
import getopt

from kademlia.network import Server
from kademlia.node import Node, NodeType
from kademlia.utils import rand_str, split_addr, ArgsParser, rand_digest_id


def usage():
	return """
Usage: python network.py -p [port] -a [bootstrap address]
-p --port
	Port on which to listen (e.g., 8000)
-a --address
	Address of node to use as bootstrap node (e.g., 127.0.0.1:8000)
	"""


def main():

	handler = logging.StreamHandler()
	formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	handler.setFormatter(formatter)
	log = logging.getLogger('kademlia')
	log.addHandler(handler)
	log.setLevel(logging.DEBUG)

	loop = asyncio.get_event_loop()
	loop.set_debug(True)

	server = Server()

	parser = ArgsParser()

	try:
		args = "p:a:"
		long_args = ["--port", "--addr="]
		opts, args = getopt.getopt(sys.argv[1:], args, long_args)
		parser.add_many(opts)
	except getopt.GetoptError as err:
		log.error("GetoptError: %s", err)
		print(usage())
		sys.exit(1)

	if parser.has_help_opt() or not parser.has_proper_opts():
		print(usage())
		sys.exit(1)

	loop.run_until_complete(server.listen_udp(int(parser.get("-p", "--port"))))

	host, port = split_addr(parser.get("-a", "--addr"))
	loop.run_until_complete(server.bootstrap([(host, port)]))

	while True:
		resource = Node(rand_digest_id(), type=NodeType.Resource, value=rand_str())
		loop.run_until_complete(server.set(resource))
		loop.run_until_complete(asyncio.sleep(5))

	try:
		loop.run_forever()
	except KeyboardInterrupt:
		print("\nAttempting to gracefully shut down...")
	finally:
		server.stop()
		loop.close()
		print("Shutdown successul")

if __name__ == "__main__":

	main()
