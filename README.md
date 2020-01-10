# Liaa 

## A Python-based Distributed Hash Table

[![Build Status](https://secure.travis-ci.org/ralston3/liaa.png?branch=master)](https://travis-ci.org/ralston3/liaa)
[![Python version](https://img.shields.io/pypi/pyversions/liaa)](https://pypi.org/project/liaa/)
![Codecov branch](https://img.shields.io/codecov/c/github/ralston3/liaa/master?color=purple)
![GitHub issues](https://img.shields.io/github/issues/ralston3/liaa?color=red)
![Repo Size](https://img.shields.io/github/repo-size/ralston3/liaa)
![GitHub commit activity](https://img.shields.io/github/commit-activity/w/ralston3/liaa)
![GitHub](https://img.shields.io/github/license/ralston3/liaa)

[This project was a fork of bmuller's original Kademlia implementation](https://github.com/bmuller/kademlia)

This library is an asynchronous Python implementation of the [Kademlia distributed hash table](http://en.wikipedia.org/wiki/Kademlia).  It relies on [asyncio](https://docs.python.org/3/library/asyncio.html) to provide fast, flexible asynchronous communication.  The peer nodes communicate using [RPC over UDP](https://en.wikipedia.org/wiki/Remote_procedure_call) to communiate, meaning that this implementation is capable of working behind a [NAT](http://en.wikipedia.org/wiki/Network_address_translation).

This library aims to be as close to a reference implementation of the [Kademlia paper](http://pdos.csail.mit.edu/~petar/papers/maymounkov-kademlia-lncs.pdf) as possible.

---
## Installation

### PyPi

```
pip install liaa
```

### Docker
```
docker pull ralston3/liaa:latest
```
---

## Examples
- [multi_peer_set.py](https://github.com/ralston3/liaa/tree/master/examples/multi_peer_set.py) - Use multiple terminal tabs to simulate a network
- [multi_peer_simulator.py](https://github.com/ralston3/liaa/tree/master/examples/multi_peer_simulator.py) - Simulates an entire multi-peer network
- [simple_peer.py](https://github.com/ralston3/liaa/tree/master/examples/simple_peer.py) - The most simplistic example of a peer on the network

---
## Usage

In order to create a peer on the network and generate some resources for it to store...

```python
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
		logger.info("Attempting to gracefully shut down...")
	finally:
		server.stop()
		logger.info("Shutdown successul")


if __name__ == "__main__":

	main()
```

---
## Initializing a Network
If you're starting a new network from scratch, just set the `-n --neighbors` flag to `False` in the command line.  
Then, bootstrap other nodes by connecting to the first node you started.

See the examples folder for a first node example that other nodes can bootstrap connect to and some code that gets and sets a key/value.

## Logging
This library uses the standard [Python logging library](https://docs.python.org/3/library/logging.html).  To see debut output printed to STDOUT, for instance, use:

```python
import logging

log = logging.getLogger('liaa')
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())
```

## Running Tests

To run the `liaa` test suite:

```
liaa git: >> make prep-dev-fresh
liaa git: >> make test
```

## Reporting Issues
Please report all issues [on github](https://github.com/ralston3/liaa/issues).

## Fidelity to Original Paper
The current implementation should be an accurate implementation of all aspects of the paper save one - in Section 2.3 there is the requirement that the original publisher of a key/value republish it every 24 hours.  This library does not do this (though you can easily do this manually).
