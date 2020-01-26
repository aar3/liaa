# simple_peer.py
#
# In this example, we demonstrate how we can simply create a peer's server,
# and listen for incoming connections. Note that this example by itself won't
# do much other than instantiate a peer and its storage.
#
# This example can be used in tandem with examples/multi_peer_set.py


# pylint: disable=wrong-import-order,unused-import
import env
import logging
import argparse
import asyncio
import sys

from liaa.server import Server
from liaa.utils import load_ssl



def main():

	handler = logging.StreamHandler()
	formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	handler.setFormatter(formatter)
	log = logging.getLogger('liaa')
	log.addHandler(handler)
	log.setLevel(logging.DEBUG)

	loop = asyncio.get_event_loop()
	loop.set_debug(True)

	parser = argparse.ArgumentParser(description='Run a single peer in the network')
	parser.add_argument('-p', '--port', help='Port to bind interfaces', required=True)
	parser.add_argument('-c', '--cert', help='Certificate for TLS')
	parser.add_argument('-k', '--key', help='Private key for TLS')
	args = vars(parser.parse_args())

	port = args.get('p') or args.get('port')
	key = args.get('k') or args.get('key')
	cert = args.get('c') or args.get('cert')

	server = Server("0.0.0.0", port)
	server.ssl_ctx = load_ssl(cert, key)
	loop.run_until_complete(server.listen())

	try:
		loop.run_forever()
	except KeyboardInterrupt:
		log.info("Attempting to gracefully shut down...")
	finally:
		server.stop()
		log.info("Shutdown successul")


if __name__ == "__main__":

	main()
