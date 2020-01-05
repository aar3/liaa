
import datetime as dt
import functools
import logging
import operator
import os
import pickle
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Iterable
from itertools import takewhile
from typing import Any, List, Optional, Tuple

from kademlia.config import CONFIG
from kademlia.node import Node, NodeType
from kademlia.utils import hex_to_int_digest

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


class IStorage(ABC):
	"""
	IStorage

	Local storage for this node.
	IStorage implementations of get must return the same type as put in by set
	"""

	@abstractmethod
	def get(self, hexkey: str, default=None) -> Optional["Node"]:
		pass

	@abstractmethod
	def set(self, node: "Node"):
		pass

	@abstractmethod
	def remove(self, hexkey: str):
		pass

	@abstractmethod
	def iter_older_than(self, seconds_old: int):
		pass

	@abstractmethod
	def prune(self):
		pass

	@abstractmethod
	def __iter__(self):
		pass

	@abstractmethod
	def __contains__(self, hexkey: str):
		pass

	@abstractmethod
	def __len__(self):
		pass


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
		self.node = node
		self.data = OrderedDict()
		self.ttl = ttl

	@pre_prune()
	def get(self, hexkey: str, default: Optional[Any] = None) -> Optional["Node"]:
		"""
		Retrieve a node from storage

		Parameters
		----------
			hexkey: str
				Hex value of node's long_id
			default: Optional[Any]
				Default value to return if node not in storage

		Returns
		-------
			Optional[Node]:
				Node if node is in storage, else `default`
		"""
		log.debug("%s fetching resource %s", self.node, hexkey)
		if hexkey in self:
			_, value = self.data[hexkey]
			return Node(hex_to_int_digest(hexkey), type=NodeType.Resource, value=value)
		log.debug("Resource %s not found on node %s", hexkey, self.node)
		return default

	def set(self, node: "Node"):
		"""
		Save a given Node in storage

		Parameters
		----------
			node: Node
				Node to be saved
		"""
		log.debug("%s setting resource %s", self.node, node.hex)
		self.data[node.hex] = (time.monotonic(), node.value)
		log.debug("%s storage has %i items", self.node, len(self))

	def remove(self, hexkey: str) -> None:
		"""
		Remove a node from storage

		Parameters
		----------
			hexkey: str
				Hex value of node's long_id
		"""
		if hexkey in self:
			log.debug("%s removing resource %s", self.node, hexkey)
			del self.data[hexkey]
			return
		log.debug("Resource %s not found on node %s", hexkey, self.node)

	def prune(self) -> None:
		"""
		Prune storage
		"""
		for _, _ in self.iter_older_than(self.ttl):
			self.data.popitem(last=False)

	def iter_older_than(self, seconds_old: int) -> List[Tuple[int, Any]]:
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
			Iterable:
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
		# pylint: disable=bad-continuation
		nodes = [Node(hex_to_int_digest(p[0]),
					type=NodeType.Resource,
					value=p[1])
			for p in zip(ikeys, ivalues)]
		for node in nodes:
			yield node

	def __contains__(self, hexkey: str) -> bool:
		return hexkey in self.data

	@pre_prune()
	def __len__(self) -> int:
		return len(self.data)


class DiskStorage(IStorage):
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
		self.node = node
		self.ttl = ttl
		self.dir = os.path.join(CONFIG.persist_dir, str(self.node.long_id))

		if not os.path.exists(self.dir):
			log.debug("creating node disk storage dir at %s", self.dir)
			os.mkdir(self.dir)

	@pre_prune()
	def get(self, hexkey: str, default: Optional[Any] = None) -> Optional["Node"]:
		"""
		Retrieve a node from storage

		Parameters
		----------
			hexkey: str
				Hex value of node's long_id
			default: Optional[Any]
				Default value to return if node not in storage

		Returns
		-------
			Optional[Node]:
				Node if node is in storage, else `default`
		"""
		log.debug("%s fetching resource %s", self.node, hexkey)
		if hexkey in self:
			# pylint: disable=bad-continuation
			return Node(hex_to_int_digest(hexkey),
							type=NodeType.Resource,
							value=self._load_data(hexkey))
		log.debug("Resource %s not found on node %s", hexkey, self.node)
		return default

	def set(self, node: "Node") -> None:
		"""
		Save a given Node in storage

		Parameters
		----------
			node: Node
				Node to be saved
		"""
		if node.hex in self:
			self.remove(node)
		log.debug("%s setting resource %s", self.node, node.hex)
		self._persist_data(node)
		log.debug("%s storage has %i items", self.node, len(self))

	def remove(self, hexkey: str) -> None:
		"""
		Remove a node from storage

		Parameters
		----------
			hexkey: str
				Hex value of node's long_id
		"""
		try:
			fname = self.dir + "/" + hexkey
			log.debug("%s removing resource %s", self.node, hexkey)
			os.remove(fname)
		except FileNotFoundError as err:
			log.debug("Resource %s not found on node %s: %s", hexkey, self.node, str(err))

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

		Returns
		-------
			List[str]:
				Contents of storage directory
		"""
		return os.listdir(self.dir)

	def _persist_data(self, node: "Node") -> None:
		"""
		Save a given node's value to disk

		Parameters
		----------
			node: Node
				The node to save
		"""
		fname = os.path.join(self.dir, node.hex)
		log.debug("%s attempting to persist %s", self.node, node.hex)
		data = {"value": node.value, "time": time.monotonic()}
		with open(fname, "wb") as ctx:
			pickle.dump(data, ctx)

	def _load_data(self, hexkey: str) -> Optional[Any]:
		"""
		Load a data at a given hexkey

		Parameters
		----------
			hexkey: str
				Hexkey to load

		Returns
		-------
			Optional[Any]:
				Data if hexkey is found, else None
		"""
		fname = os.path.join(self.dir, hexkey)
		log.debug("%s attempting to read resource node at %s", self.node, hexkey)
		try:
			with open(fname, "rb") as ctx:
				data = pickle.load(ctx)
				return data["value"]
		except FileNotFoundError as err:
			log.error("%s could not load key at %s: %s", self.node, hexkey, str(err))

	def _content_stats(self) -> List[Tuple[str, float]]:
		"""
		For each node in storage, return its 'last modified time'

		Returns
		-------
			List[Tuple[str, float]]
				List of (filename, last_modified_time) pairs
		"""
		def time_delta(hexkey: str) -> Tuple[str, float]:
			path = os.path.join(self.dir, hexkey)
			statbuff = os.stat(path)
			diff = dt.datetime.fromtimestamp(time.time()) - dt.datetime.fromtimestamp(statbuff.st_mtime)
			return hexkey, diff.seconds
		return list(map(time_delta, self.contents()))

	@pre_prune()
	def __iter__(self) -> Iterable:
		log.debug("%s iterating over %i items in storage", self.node, len(self.contents()))
		ikeys = self.contents()
		ivalues = [self._load_data(k) for k in ikeys]
		# pylint: disable=bad-continuation
		nodes = [Node(hex_to_int_digest(p[0]),
							type=NodeType.Resource,
							value=p[1])
					for p in zip(ikeys, ivalues)]
		for node in nodes:
			yield node

	def __contains__(self, hexkey: str) -> bool:
		return hexkey in self.contents()

	@pre_prune()
	def __repr__(self) -> str:
		return repr(self.contents())

	@pre_prune()
	def __len__(self) -> int:
		return len(self.contents())


StorageIface = EphemeralStorage
