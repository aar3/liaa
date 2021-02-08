# Liaa 

<img src="./logo.png" alt="drawing" width="160"/>

## Cache-based distributed P2P network abstraction using the Kademlia protocol

[![Build Status](https://secure.travis-ci.org/aar3/liaa.png?branch=master)](https://travis-ci.org/aar3/liaa)
[![Python version](https://img.shields.io/pypi/pyversions/liaa)](https://pypi.org/project/liaa/)
![Codecov branch](https://img.shields.io/codecov/c/github/aar3/liaa/master?color=purple)
![GitHub issues](https://img.shields.io/github/issues/aar3/liaa?color=red)
![Repo Size](https://img.shields.io/github/repo-size/aar3/liaa)
![GitHub commit activity](https://img.shields.io/github/commit-activity/w/aar3/liaa)
![GitHub](https://img.shields.io/github/license/aar3/liaa)


This library is an asynchronous Python implementation of the [Kademlia distributed hash table](http://en.wikipedia.org/wiki/Kademlia).  It relies on [asyncio](https://docs.python.org/3/library/asyncio.html) to provide fast, flexible asynchronous communication.  The peer nodes communicate using [RPC over UDP](https://en.wikipedia.org/wiki/Remote_procedure_call) to communiate, meaning that this implementation is capable of working behind a [NAT](http://en.wikipedia.org/wiki/Network_address_translation).

This library aims to be as close to a reference implementation of the [Kademlia paper](http://pdos.csail.mit.edu/~petar/papers/maymounkov-kademlia-lncs.pdf) as possible.

