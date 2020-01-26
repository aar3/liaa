# Liaa 

<img src="./logo.png" alt="drawing" width="160"/>

## A Distributed Hash Table

[![Build Status](https://secure.travis-ci.org/ralston3/liaa.png?branch=master)](https://travis-ci.org/ralston3/liaa)
[![Python version](https://img.shields.io/pypi/pyversions/liaa)](https://pypi.org/project/liaa/)
![Codecov branch](https://img.shields.io/codecov/c/github/ralston3/liaa/master?color=purple)
![GitHub issues](https://img.shields.io/github/issues/ralston3/liaa?color=red)
![Repo Size](https://img.shields.io/github/repo-size/ralston3/liaa)
![GitHub commit activity](https://img.shields.io/github/commit-activity/w/ralston3/liaa)
![GitHub](https://img.shields.io/github/license/ralston3/liaa)


This library is an asynchronous Python implementation of the [Kademlia distributed hash table](http://en.wikipedia.org/wiki/Kademlia).  It relies on [asyncio](https://docs.python.org/3/library/asyncio.html) to provide fast, flexible asynchronous communication.  The peer nodes communicate using [RPC over UDP](https://en.wikipedia.org/wiki/Remote_procedure_call) to communiate, meaning that this implementation is capable of working behind a [NAT](http://en.wikipedia.org/wiki/Network_address_translation).

This library aims to be as close to a reference implementation of the [Kademlia paper](http://pdos.csail.mit.edu/~petar/papers/maymounkov-kademlia-lncs.pdf) as possible.

&nbsp;
## Installation

PyPi

```
pip install liaa
```

Docker <strong>(this is experimental only, do not use at this time)</strong>
```
docker pull ralston3/liaa:latest
```

Github
```
git clone git@github.com:ralston3/liaa.git && cd liaa/
make prep-dev-lock
make test
```

&nbsp;

## Examples
- [multi_peer_set.py](https://github.com/ralston3/liaa/tree/master/examples/multi_peer_set.py)
   - Use multiple terminal tabs to simulate a network
   - Does not simulate `GET` requests (TODO)

- [multi_peer_simulator.py](https://github.com/ralston3/liaa/tree/master/examples/multi_peer_simulator.py)
   - Simulates an entire multi-peer network
   - Does not simulate `GET` requests (TODO)

- [simple_peer.py](https://github.com/ralston3/liaa/tree/master/examples/simple_peer.py) 
   - The most simplistic example of a peer on the network

&nbsp;

## Usage

In order to create a peer on the network and generate some resources for it to store...

```python
import logging
import argparse
import asyncio

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

	parser = argparse.ArgumentParser(description='Run a peer as an app in the network')
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
```

&nbsp;

## Initializing a Network
If you're starting a new network from scratch, just set the `-n --neighbors` flag to `False` in the command line.  
Then, bootstrap other nodes by connecting to the first node you started.

See the examples folder for a first node example that other nodes can bootstrap connect to and some code that gets and sets a key/value.

&nbsp;

## Logging
This library uses the standard [Python logging library](https://docs.python.org/3/library/logging.html).  To see debut output printed to STDOUT, for instance, use:

```python
import logging

log = logging.getLogger('liaa')
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())
```

&nbsp;

## Running Tests

To run the `liaa` test suite:

```
pytest tests/*
```

&nbsp;

## Reporting Issues
Please report all issues [on github](https://github.com/ralston3/liaa/issues).

&nbsp;

## Fidelity to Original Paper
The current implementation should be an accurate implementation of all aspects of the paper save one - in Section 2.3 there is the requirement that the original publisher of a key/value republish it every 24 hours.  This library does not do this (though you can easily do this manually).

&nbsp;

This project was started as a fork of [@bmuller's original Kademlia implementation](https://github.com/bmuller/kademlia)