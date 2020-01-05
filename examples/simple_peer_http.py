# simple_peer_http.py
#
# Same as examples/simple_peer_udp.py but using http
#
# Example
# -------
# python examples/simple_peer_http.py -p 8000

import logging
import asyncio
import sys
import getopt

from kademlia.network import Server
from kademlia.utils import ArgsParser


def usage():
	return """
Usage: python network.py -p [port]
-p --port
	Port on which to listen (e.g., 8000)
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

	parser = ArgsParser()

	try:
		args = "p:"
		long_args = ["--port"]
		opts, args = getopt.getopt(sys.argv[1:], args, long_args)
		parser.add_many(opts)
	except getopt.GetoptError as err:
		log.error("GetoptError: %s", err)
		print(usage())
		sys.exit(1)

	if parser.has_help_opt() or not parser.has_proper_opts():
		print(usage())
		sys.exit(1)

	server = Server()
	loop.run_until_complete(server.listen_http(int(parser.get("-p", "--port"))))

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
