# CHANGELOG

### 12.15.19
- [fork] fork original repo at https://github.com/bmuller/kademlia
- [enhancement] add unit test coverage to all modules
- [enhancement] add rpc module (similar to protocol but segmenting rpc from kademlia)
   - Datagram
   - RPCMessageQueue
### 12.22.19
- [enhancement] add CI support
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
### 1.5.19
   - [refactor] remove config
   - [enhancement] add Docker support
   - [chore] rename project to `liaa` to avoid pypi namespace collisions
   - [bugfix] ensure crawler working properly (ISSUE-28)
      - remove kademlia/ sphinx docs
      - update CI to push on version branches and master
      - base node IDs off of ip:port, and search keys and adjust tests
   - [enhancement] add self-signed tls to http iface
   - [technical] verify crawling implementation and add tests
### 1.12.19
   - [enhancement] continue adding tests and dostctrings
   - [enhancement] add quantitative network analyses to confirm implementation
   - [enhancement] add various features of the paper
      - swap getopt parser for argeparse