# CHANGELOG

### 12.15.19
- [fork] fork original repo at https://github.com/bmuller/kademlia
- [enhancement] add unit test coverage to all modules
- [enhancement] add rpc module (similar to protocol but segmenting rpc from kademlia)
   - Datagram
   - RPCMessageQueue
### 12.22.19
- [enhancement] add CI support
   - add Docker support
   - add travis support
   - add code coverage support
- [enhancement] add logging
   - distinguish between Node, Peer, and Resource
- [enhancement] add disk storage implementation
### 12.29.19
- [refactor] refactor storage implementation for cohesiveness
   - use hex keys to storage resources (long_id not good for umsgpack)
- [enhancement] create multi-peer working examples (examples/multi_peer_simulator.py)
- [enhancement] add tcp listener on server
   - remove Datagram abstraction
   - remove RPCMessageQueue abstraction
