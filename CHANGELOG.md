# CHANGELOG

### 12.15.19
- [fork] fork original repo at https://github.com/bmuller/kademlia
- [enhancement] add unit test coverage to all modules
- [enhancement] augment protocol module with a few abstractions
- [enhancement] add rpc module (similar to protocol but segmenting rpc from kademlia)
   - Datagram
   - RPCMessageQueue
- [chore] add docstrings and typings

### 12.22.19
- [chore] cleanup docstrings and types for all modules
   - add docstrings and typings
   - change some naming for more clarity/explicitness
- [enhancement] add tests for protocol module
- [enhancement] add CI support
   - add Docker support
   - add travis support
   - add code coverage support
- [enhancement] create multi-peer working examples (examples/network.py)

- [enhancement] add coveralls support - https://coveralls.io
- [enhancement] add logging
   - distinguish between Node, Peer, and Resource
- [enhancement] add disk storage implementation
- [refactor] refactor storage implementation for cohesiveness
   - use StorageIface to simplify storage setting throughout app
   - use IStorage ABC as a true base class for all storage implementations
   - use hex keys to storage resources, and keep long_id non-storage references
