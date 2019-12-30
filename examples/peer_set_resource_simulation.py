import logging
import asyncio
import sys
import getopt

from kademlia.network import Server
from kademlia.node import Node, NodeType
from kademlia.utils import rand_int_id, rand_str, split_addr, ArgsParser, int_to_digest


def network_example_usage():
	return """
Usage: python network.py -p [port] -a [bootstrap address]
-p --port
	Port on which to listen (e.g., 8000)
-a --address
	Address of node to use as bootstrap node (e.g., 127.0.0.1:8000)
	"""


def main():

	# create a basic 'kademlia' stream logger and set it as our default handler
	handler = logging.StreamHandler()
	formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	handler.setFormatter(formatter)
	log = logging.getLogger('kademlia')
	log.addHandler(handler)
	log.setLevel(logging.DEBUG)

	loop = asyncio.get_event_loop()
	loop.set_debug(True)

	# create our server, which will be our public interface to interact with
	# other nodes/peers in the network. any action communicated via rpc will
	# first be commited to a `server` instance
	server = Server()

	# create our ArgsParser, which will be used to parse command line
	# args used to start example
	parser = ArgsParser()

	try:

		# the flags and options that this example accepts
		args = "p:a:"
		long_args = ["--port", "--addr="]

		# use getopt to parse our args and add them to our parser
		opts, args = getopt.getopt(sys.argv[1:], args, long_args)
		parser.add_many(opts)

	except getopt.GetoptError as err:

		# if we experience a getopt error for some reason, just log the error,
		# show usage, and exit
		log.error("GetoptError: %s", err)
		print(network_example_usage())
		sys.exit(1)

	# if we don't have all the necessary args to start the example, or if
	# we get a 'help' arg, just show usage and exit
	if parser.has_help_opt() or not parser.has_proper_opts():
		print(network_example_usage())
		sys.exit(1)


	# run our server's listener using the port we passed in
	loop.run_until_complete(server.listen(int(parser.get("-p", "--port"))))

	# split the bootstrap node address that we passed in and use that to
	# bootstrap our server
	host, port = split_addr(parser.get("-a", "--addr"))
	loop.run_until_complete(server.bootstrap([(host, port)]))

	# here we just run some random actions in a loop to ensure that the protocol
	# works as specified. we generate a random resource to be stored on the
	# network and store it on our node (we can verify via logs that this
	# resource was properly shared through the network)
	while True:

		# create a resource node and set it on our current routing table
		int_id = rand_int_id()
		resource = Node(int_to_digest(int_id), type=NodeType.Resource, value=rand_str())
		loop.run_until_complete(server.set(resource))
		loop.run_until_complete(asyncio.sleep(5))

	# we should shutdown gracefully
	try:
		loop.run_forever()
	except KeyboardInterrupt:
		pass
	finally:
		server.stop()
		loop.close()

if __name__ == "__main__":

	main()
