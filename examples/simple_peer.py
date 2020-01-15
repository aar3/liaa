# simple_peer.py
#
# In this example, we demonstrate how we can simply create a peer's server,
# and listen for incoming connections. Note that this example by itself won't
# do much other than instantiate a peer and its storage.
#
# This example can be used in tandem with examples/multi_peer_set.py
#
# Example
# -------
# python examples/simple_peer.py -p 8000

import env

import logging
import asyncio
import sys
import getopt

from liaa.network import Server
from liaa.utils import ArgsParser, debug_ssl_ctx


def usage():
	return """
Usage: python simple_peer.py -p [port]
-p --port
	Port on which to listen (e.g., 8000)
	"""

def main():

	handler = logging.StreamHandler()
	formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	handler.setFormatter(formatter)
	log = logging.getLogger('liaa')
	log.addHandler(handler)
	log.setLevel(logging.DEBUG)

	loop = asyncio.get_event_loop()
	loop.set_debug(True)

	parser = ArgsParser()

	try:
		opts, _ = getopt.getopt(sys.argv[1:], "p:", ["--port"])
		parser.add_many(opts)
	except getopt.GetoptError as err:
		log.error("GetoptError: %s", err)
		print(usage())
		sys.exit(1)

	if parser.has_help_opt() or not parser.has_proper_opts():
		print(usage())
		sys.exit(1)

	server = Server("0.0.0.0", int(parser.get("-p", "--port")))
	server.ssl_ctx = debug_ssl_ctx(server.storage.root_dir)
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
