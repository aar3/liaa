
import datetime as dt
import functools
import logging
import operator
import os
import pickle
import time
from collections import OrderedDict
from collections.abc import Iterable
from itertools import takewhile
from typing import Any, List, Optional, Tuple

from liaa.node import Node, NodeType

log = logging.getLogger(__name__)  # pylint: disable=invalid-name


def pre_prune():
	"""
	Decorator (syntactic sugar) for a storage interface's `prune()`
	method
	"""
	def wrapper(func):
		@functools.wraps(func)
		def _pre_prune(*args):
			"""
			Parameters
			----------
				args[0]: IStorage
					Reference to instance of storae interface
			"""
			log.debug("%s pruning items...", args[0].node)
			args[0].prune()
			return func(*args)
		return _pre_prune
	return wrapper


# pylint: disable=too-few-public-methods
class IStorage:
	"""
	IStorage

	Parameters
	----------
		node: Node
			The node representing this peer
		ttl: int
			Max age that items can live untouched before being pruned
			(default=604800 seconds = 1 week)
	"""
	def __init__(self, node: "Node", ttl: int = 604800):
		self.node = node
		self.ttl = ttl
		kstore_dir = os.path.join(os.path.expanduser("~"), ".liaa")
		if not os.path.exists(kstore_dir):
			log.debug("Liaa dir at %s not found, creating...", kstore_dir)
			os.mkdir(kstore_dir)

		self.dir = os.path.join(kstore_dir, str(self.node.long_id))
		if not os.path.exists(self.dir):
			log.debug("Node dir at %s not found, creating...", self.dir)
			os.mkdir(self.dir)


class EphemeralStorage(IStorage):
	def __init__(self, node: "Node", ttl=604800):
		"""
		EphemeralStorage

		Parameters
		----------
			node: Node
				The node representing this peer
			ttl: int
			Max age that items can live untouched before being pruned
				(default=604800 seconds = 1 week)
		"""
		super(EphemeralStorage, self).__init__(node, ttl)
		self.data = OrderedDict()

	@pre_prune()
	def get(self, key: str, default: Optional[bytes] = None) -> Optional["Node"]:
		"""
		Retrieve a node from storage

		Parameters
		----------
			key: str
				Key of node to be fetched
			default: Optional[bytes]
				Default value to return if node not in storage

		Returns
		-------
			Optional[Node]:
				Node if node is in storage, else `default`
		"""
		log.debug("%s fetching Node %s", self.node, key)
		if key in self:
			_, value = self.data[key]
			return Node(key=key, node_type=NodeType.Resource, value=value)
		log.debug("Node %s not found on node %s", key, self.node)
		return default

	def set(self, node: "Node"):
		"""
		Save a given Node in storage

		Parameters
		----------
			node: Node
				Node to be saved
		"""
		log.debug("%s setting node %s", self.node, node.key)
		if node in self:
			self.remove(node.key)
		self.data[node.key] = (time.monotonic(), node.value)
		log.debug("%s storage has %i items", self.node, len(self))

	def remove(self, key: str) -> None:
		"""
		Remove a node from storage

		Parameters
		----------
			key: str
				Key of node to be removed
		"""
		assert key in self
		log.debug("%s removing resource %s", self.node, key)
		del self.data[key]
		log.debug("Resource %s not found on node %s", key, self.node)

	def prune(self) -> None:
		"""
		Prune storage
		"""
		for _, _ in self.iter_older_than(self.ttl):
			self.data.popitem(last=False)

	def iter_older_than(self, seconds_old: int) -> List[Tuple[int, bytes]]:
		"""
		Return nodes that are older than `seconds_old`

		** For EphemeralStorage we use operator.itemgetter(0, 2) in order to
		return just keys and values (without time.monotonic())

		Parameters
		----------
			seconds_old: int
				Time threshold (seconds)

		Returns
		-------
			List[Tuple[int, bytes]]:
				Zipped keys, and values of nodes that are older that `seconds_old`
		"""
		min_birthday = time.monotonic() - seconds_old
		zipped = self._triple_iter()
		matches = takewhile(lambda r: min_birthday >= r[1], zipped)
		items = list(map(operator.itemgetter(0, 2), matches))
		log.debug("%s returning %i nodes for republishing....", self.node, len(items))
		return items

	def _triple_iter(self) -> Iterable:
		"""
		Iterate over EphermeralStorage to return each contents key, time,
		and values
		"""
		ikeys = self.data.keys()
		ibirthday = map(operator.itemgetter(0), self.data.values())
		ivalues = map(operator.itemgetter(1), self.data.values())
		return zip(ikeys, ibirthday, ivalues)

	@pre_prune()
	def __repr__(self) -> str:
		return repr(self.data)

	@pre_prune()
	def __iter__(self) -> Iterable:
		log.debug("%s iterating over %i items in storage", self.node, len(self.data))
		ikeys = self.data.keys()
		ivalues = map(operator.itemgetter(1), self.data.values())
		nodes = [Node(key=p[0], node_type=NodeType.Resource, value=p[1]) for p in zip(ikeys, ivalues)]

		for node in nodes:
			yield node

	def __contains__(self, key: str) -> bool:
		return key in self.data

	@pre_prune()
	def __len__(self) -> int:
		return len(self.data)


class DiskStorage(IStorage):
	# pylint: disable=bad-continuation
	def __init__(self, node: "Node", ttl=604800):
		"""
		DiskStorage

		Parameters
		----------
			node: Node
				The node representing this peer
			ttl: int
				Max age that items can live untouched before being pruned
				(default=604800 seconds = 1 week)
		"""
		super(DiskStorage, self).__init__(node, ttl)
		self.content_dir = os.path.join(self.dir, "content")
		if not os.path.exists(self.content_dir):
			log.debug("Node content dir at %s not found, creating...", self.content_dir)
			os.mkdir(self.content_dir)

	@pre_prune()
	def get(self, key: str, default: Optional[bytes] = None) -> Optional["Node"]:
		"""
		Retrieve a node from storage

		Parameters
		----------
			key: str
				Key of node to be fetched
			default: Optional[bytes]
				Default value to return if node not in storage

		Returns
		-------
			Optional[Node]:
				Node if node is in storage, else `default`
		"""
		log.debug("%s fetching node %s", self.node, key)
		if key in self:
			return Node(key=key, node_type=NodeType.Resource, value=self._load_data(key))
		log.debug("Node %s not found on node %s", key, self.node)
		return default

	def set(self, node: "Node") -> None:
		"""
		Save a given Node in storage

		Parameters
		----------
			node: Node
				Node to be saved
		"""
		if node.key in self:
			self.remove(node.key)
		log.debug("%s setting node %s", self.node, node.key)
		self._persist_data(node)
		log.debug("%s storage has %i items", self.node, len(self))

	def remove(self, key: str) -> None:
		"""
		Remove a node from storage

		Parameters
		----------
			key: str
				Key of node to be removed
		"""
		assert key in self
		fname = os.path.join(self.content_dir, key)
		log.debug("%s removing node %s", self.node, key)
		os.remove(fname)

	def iter_older_than(self, seconds_old: int) -> Iterable:
		"""
		Return nodes that are older than `seconds_old`

		Parameters
		----------
			seconds_old: int
				Time threshold (seconds)

		Returns
		-------
			Iterable:
				Zipped keys, and values of nodes that are older that `seconds_old`
		"""
		to_republish = filter(lambda t: t[1] > seconds_old, self._content_stats())
		repub_keys = list(map(operator.itemgetter(0), to_republish))
		repub_data = [self._load_data(k) for k in repub_keys]
		log.debug("%s returning %i nodes for republishing....", self.node, len(repub_keys))
		return zip(repub_keys, repub_data)

	def prune(self) -> None:
		"""
		Prune storage
		"""
		for key, _ in self.iter_older_than(self.ttl):
			self.remove(key)

	def contents(self) -> List[str]:
		"""
		List all nodes in storage

		TODO: ideally, we shouldn't have to filter out the state file
		like this, we should maybe keep all config/state files in the parent
		directory, and the actual data files in a sub-directory

		Returns
		-------
			List[str]:
				Contents of storage directory
		"""
		return os.listdir(self.content_dir)

	def _persist_data(self, node: "Node") -> None:
		"""
		Save a given node's value to disk

		Parameters
		----------
			node: Node
				The node to save
		"""
		fname = os.path.join(self.content_dir, node.key)
		log.debug("%s attempting to persist %s", self.node, node.key)
		data = {"value": node.value, "time": time.monotonic()}
		with open(fname, "wb") as ctx:
			pickle.dump(data, ctx)

	def _load_data(self, key: str) -> Optional[bytes]:
		"""
		Load a data at a given key

		Parameters
		----------
			key: str
				Key of data to load

		Returns
		-------
			Optional[bytes]:
				Data if key is found, else None
		"""
		fname = os.path.join(self.content_dir, key)
		log.debug("%s attempting to read node at %s", self.node, key)
		try:
			with open(fname, "rb") as ctx:
				data = pickle.load(ctx)
				return data["value"]
		except FileNotFoundError as err:
			log.error("%s could not load key at %s: %s", self.node, key, str(err))

	def _content_stats(self) -> List[Tuple[str, float]]:
		"""
		For each node in storage, return its 'last modified time'

		Returns
		-------
			List[Tuple[str, float]]
				List of (filename, last_modified_time) pairs
		"""
		def time_delta(key: str) -> Tuple[str, float]:
			path = os.path.join(self.content_dir, key)
			statbuff = os.stat(path)
			diff = dt.datetime.fromtimestamp(time.time()) - dt.datetime.fromtimestamp(statbuff.st_mtime)
			return key, diff.seconds
		return list(map(time_delta, self.contents()))

	@pre_prune()
	def __iter__(self) -> Iterable:
		log.debug("%s iterating over %i items in storage", self.node, len(self.contents()))
		ikeys = self.contents()
		ivalues = [self._load_data(k) for k in ikeys]
		nodes = [Node(key=p[0], node_type=NodeType.Resource, value=p[1]) for p in zip(ikeys, ivalues)]
		for node in nodes:
			yield node

	def __contains__(self, key: str) -> bool:
		return key in self.contents()

	@pre_prune()
	def __repr__(self) -> str:
		return repr(self.contents())

	@pre_prune()
	def __len__(self) -> int:
		return len(self.contents())


StorageIface = DiskStorage
