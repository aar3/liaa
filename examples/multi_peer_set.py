# multi_peer_set.py
#
# In this example, we merely instantiate a single peer using a given port, and
# boostrap peer address (provided via command line args) and run a loop that
# creates a random resource and sets it on this peer's server.
#
# The idea is that we open a few terminal tabs, and run this program using a few
# different ports, in order to ensure that the network is behaving as expected


# pylint: disable=wrong-import-order,unused-import
import env
import logging
import asyncio
import argparse
import time
import sys
import getopt

from liaa.network import Server
from liaa.node import ResourceNode, PeerNode
from liaa.utils import rand_str, split_addr, load_ssl


async def make_fake_data(server):
	while True:
		node = ResourceNode(key=rand_str(), value=rand_str().encode())
		await server.set(node)
		await asyncio.sleep(5)


def main():

	handler = logging.StreamHandler()
	formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	handler.setFormatter(formatter)
	log = logging.getLogger('liaa')
	log.addHandler(handler)
	log.setLevel(logging.DEBUG)

	loop = asyncio.get_event_loop()


	parser = argparse.ArgumentParser(description='Run a single peer in the network')
	parser.add_argument('-p', '--port', help='Port to bind interfaces', required=True)
	parser.add_argument('-n', '--neighbors', nargs='+', help='Neighbors to boostrap with')
	parser.add_argument('-c', '--cert', help='Certificate for TLS')
	parser.add_argument('-k', '--key', help='Private key for TLS')
	args = vars(parser.parse_args())

	port = args.get('p') or args.get('port')
	bootstrap_peers = (args.get('neighbors') or args.get('n')) or []
	key = args.get('k') or args.get('key')
	cert = args.get('c') or args.get('cert')

	server = Server("0.0.0.0", port)
	server.ssl_ctx = load_ssl(cert, key)

	loop.run_until_complete(server.listen())


	if bootstrap_peers:
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
