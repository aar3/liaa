import logging
import asyncio
import sys
import getopt

from liaa.network import Server
from liaa.utils import ArgsParser, split_addr, str_arg_to_bool


def usage():
	return """
Usage: python app.py -p [port] -n [bootstrap neighbors]
-p --port
	Port on which to listen (e.g., 8000)
-n --neighbors
	Neighbors with which to bootstrap (e.g., 177.91.19.1:8000,178.31.13.21:9876)
		or 'False' if not passing an args
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
		opts, _ = getopt.getopt(sys.argv[1:], "p:n:", ["--port", "--neighbors"])
		parser.add_many(opts)
	except getopt.GetoptError as err:
		log.error("GetoptError: %s", err)
		print(usage())
		sys.exit(1)

	if parser.has_help_opt() or not parser.has_proper_opts():
		print(usage())
		sys.exit(1)

	server = Server()
	loop.run_until_complete(server.listen(int(parser.get("-p", "--port"))))

	bootstrap_peers = str_arg_to_bool(parser.get("-n", "--neighbors"))
	if bootstrap_peers:
		bootstrap_peers = bootstrap_peers.split(",")
		loop.create_task(server.bootstrap(list(map(split_addr, bootstrap_peers))))

	try:
		loop.run_forever()
	except KeyboardInterrupt:
		print("\nAttempting to gracefully shut down...")
	finally:
		server.stop()
		print("Shutdown successul")


if __name__ == "__main__":

	main()
