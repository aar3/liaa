# CHANGELOG

### 12.15.19
- [fork] fork original repo at https://github.com/bmuller/kademlia
- [enhancement] add rpc module (similar to protocol but segmenting rpc from kademlia)
### 12.22.19
- [enhancement] add CI support (travis.yml, codecov)
- [enhancement] add disk storage implementation
### 12.29.19
- [enhancement] create multi-peer working examples (examples/multi_peer_simulator.py)
- [enhancement] add http listener on server to work with udp port
### 1.5.19
   - [enhancement] add Docker support
   - [chore] rename project to `liaa` to avoid pypi namespace collisions
   - [bugfix] ensure crawler working properly (ISSUE-28)
      - update CI to push on version branches and master
      - base node IDs off of ip:port, and search keys and adjust tests
### 1.12.19
   - [enhancement] add tls to http iface
### 1.19.19
   - [enhancement] add various features of the paper
      - swap getopt parser for argeparse
      - swap ordereddict kbucket node cache for LRU cache
### 1.27.19
- [enhancement] add quantitative network analyses to confirm implementation