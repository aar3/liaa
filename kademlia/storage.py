
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
	def get(self, hexkey: str, default=None):
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
	def get(self, hexkey: str, default: Optional[Any] = None) -> Any:
		return self.data.get(hexkey, default)

	def set(self, node: "Node"):
		self.data[node.hex] = (time.monotonic(), node.value)

	def remove(self, hexkey: str) -> None:
		if hexkey in self:
			del self.data[hexkey]

	def prune(self) -> None:
		for _, _ in self.iter_older_than(self.ttl):
			self.data.popitem(last=False)

	def iter_older_than(self, seconds_old: int) -> List[Tuple[int, Any]]:
		"""
		Here we use operator.itemgetter(0, 2) in order to return just
		keys and values (without time.monotonic())
		"""
		min_birthday = time.monotonic() - seconds_old
		zipped = self._triple_iter()
		matches = takewhile(lambda r: min_birthday >= r[1], zipped)
		return list(map(operator.itemgetter(0, 2), matches))

	def _triple_iter(self) -> Iterable:
		ikeys = self.data.keys()
		ibirthday = map(operator.itemgetter(0), self.data.values())
		ivalues = map(operator.itemgetter(1), self.data.values())
		return zip(ikeys, ibirthday, ivalues)

	@pre_prune()
	def __repr__(self) -> str:
		return repr(self.data)

	@pre_prune()
	def __iter__(self) -> Iterable:
		ikeys = self.data.keys()
		ivalues = map(operator.itemgetter(1), self.data.values())
		return zip(ikeys, ivalues)

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
	def get(self, hexkey: str, default=None) -> "Node":
		if hexkey in self:
			# pylint: disable=bad-continuation
			return Node(hex_to_int_digest(hexkey),
							type=NodeType.Resource,
							value=self._load_data(hexkey))
		return default

	def set(self, node: "Node") -> None:
		if node.hex in self:
			self.remove(node)
		self._persist_data(node)

	def remove(self, hexkey: str) -> None:
		try:
			fname = self.dir + "/" + hexkey
			log.debug("%s removing resource %s", self.node, hexkey)
			os.remove(fname)
		except FileNotFoundError as err:
			log.error("%s could not remove key %s: %s", self.node, hexkey, str(err))

	def iter_older_than(self, seconds_old: int) -> Iterable:
		to_republish = filter(lambda t: t[1] > seconds_old, self._content_stats())
		repub_keys = list(map(operator.itemgetter(0), to_republish))
		repub_data = [self._load_data(k) for k in repub_keys]
		return zip(repub_keys, repub_data)

	def prune(self) -> None:
		for key, _ in self.iter_older_than(self.ttl):
			self.remove(key)

	def contents(self) -> List[str]:
		return os.listdir(self.dir)

	def _persist_data(self, node: "Node") -> None:
		fname = os.path.join(self.dir, node.hex)
		log.debug("%s attempting to persist %s", self.node, node.hex)
		data = {"value": node.value, "time": time.monotonic()}
		with open(fname, "wb") as ctx:
			pickle.dump(data, ctx)

	def _load_data(self, hexkey: str) -> Optional[Any]:
		fname = os.path.join(self.dir, hexkey)
		log.debug("%s attempting to read resource node at %s", self.node, hexkey)
		try:
			with open(fname, "rb") as ctx:
				data = pickle.load(ctx)
				return data["value"]
		except FileNotFoundError as err:
			log.error("%s could not load key at %s: %s", self.node, hexkey, str(err))

	def _content_stats(self) -> List[Tuple[str, float]]:
		def time_delta(hexkey: str) -> Tuple[str, float]:
			path = os.path.join(self.dir, hexkey)
			statbuff = os.stat(path)
			diff = dt.datetime.fromtimestamp(time.time()) - dt.datetime.fromtimestamp(statbuff.st_mtime)
			return hexkey, diff.seconds
		return list(map(time_delta, self.contents()))

	@pre_prune()
	def __iter__(self) -> Iterable:
		ikeys = self.contents()
		ivalues = [self._load_data(k) for k in ikeys]
		return zip(ikeys, ivalues)

	def __contains__(self, hexkey: str) -> bool:
		return hexkey in self.contents()

	@pre_prune()
	def __repr__(self) -> str:
		return repr(self.contents())

	@pre_prune()
	def __len__(self) -> int:
		return len(self.contents())


StorageIface = EphemeralStorage
