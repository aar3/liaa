import time
import os
from itertools import takewhile
import operator
import logging
import datetime as dt
import pickle
import functools
from collections import OrderedDict
from abc import abstractmethod, ABC
from typing import List, Optional, Tuple

from kademlia.config import CONFIG
from kademlia.utils import int_to_digest
from kademlia.node import NodeType, Node

log = logging.getLogger(__name__)  # pylint: disable=invalid-name



def pre_prune():
	def wrapper(func):
		@functools.wraps(func)
		def _pre_prune(*args):
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
	def get(self, key, default=None):
		"""
		Get given key.  If not found, return default.
		"""

	@abstractmethod
	def set(self, node: "Node"):
		"""
		Get given key.  If not found, return default.
		"""

	@abstractmethod
	def iter_older_than(self, seconds_old):
		"""
		Return the an iterator over (key, value) tuples for items older
		than the given secondsOld.
		"""

	@abstractmethod
	def __iter__(self):
		"""
		Get the iterator for this storage, should yield tuple of (key, value)
		"""


class EphemeralStorage(IStorage):
	def __init__(self, ttl=604800):
		"""
		Ephemeral Storage

		Parameters
		----------
			ttl: int
				Max age that items can live untouched before being pruned
				(default=604800 seconds = 1 week)
		"""
		self.data = OrderedDict()
		self.ttl = ttl

	def __setitem__(self, key, value):
		if key in self.data:
			del self.data[key]
		self.data[key] = (time.monotonic(), value)
		self.prune()

	def prune(self):
		for _, _ in self.iter_older_than(self.ttl):
			self.data.popitem(last=False)

	def get(self, key, default=None):
		self.prune()
		if key in self.data:
			return self[key]
		return default

	def set(self, node):
		self[node.key] = node.value

	def __getitem__(self, key):
		self.prune()
		return self.data[key][1]

	def __repr__(self):
		self.prune()
		return repr(self.data)

	def iter_older_than(self, seconds_old):
		min_birthday = time.monotonic() - seconds_old
		zipped = self._triple_iter()
		matches = takewhile(lambda r: min_birthday >= r[1], zipped)
		return list(map(operator.itemgetter(0, 2), matches))

	def _triple_iter(self):
		ikeys = self.data.keys()
		ibirthday = map(operator.itemgetter(0), self.data.values())
		ivalues = map(operator.itemgetter(1), self.data.values())
		return zip(ikeys, ibirthday, ivalues)

	def __iter__(self):
		ikeys = self.data.keys()
		ivalues = map(operator.itemgetter(1), self.data.values())
		return zip(ikeys, ivalues)




class DiskStorage(IStorage):
	def __init__(self, node: "Node", ttl=604800):
		"""
		DiskStorage

		Parameters
		----------
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

	def prune(self) -> None:
		for key, _ in self.iter_older_than(self.ttl):
			self.remove(key)

	@pre_prune()
	def set(self, node: "Node"):
		if node in self:
			self.remove(node)
		self.persist_data(node)

	@pre_prune()
	def get(self, key: int, default=None) -> "Node":
		if key in self:
			# pylint: disable=bad-continuation
			return Node(digest_id=int_to_digest(key),
							type=NodeType.Resource,
							value=self.load_data(key))
		return default

	def contents(self) -> List[str]:
		return os.listdir(self.dir)

	def remove(self, key: int) -> None:
		try:
			fname = self.dir + "/" + str(key)
			log.debug("%s removing resource %i", self.node, key)
			os.remove(fname)
		except FileNotFoundError as err:
			log.error("%s could not remove key %i: %s", self.node, key, str(err))

	def persist_data(self, node: "Node") -> None:
		fname = os.path.join(self.dir, str(node.long_id))
		log.debug("%s attempting to persist %i", self.node, node.long_id)
		data = {"value": node.value, "time": time.monotonic()}
		with open(fname, "wb") as ctx:
			pickle.dump(data, ctx)

	def load_data(self, key: int) -> Optional[Tuple[float, bytes]]:
		fname = os.path.join(self.dir, str(key))
		log.debug("%s attempting to read resource node at %i", self.node, key)
		try:
			with open(fname, "rb") as ctx:
				data = pickle.load(ctx)
				return data["value"]
		except FileNotFoundError as err:
			log.error("%s could not load key at %i: %s", self.node, key, str(err))

	def content_stats(self):
		def time_delta(name):
			path = os.path.join(self.dir, name)
			statbuff = os.stat(path)
			diff = dt.datetime.fromtimestamp(time.time()) - dt.datetime.fromtimestamp(statbuff.st_mtime)
			return name, diff.seconds
		return list(map(time_delta, self.contents()))

	def iter_older_than(self, seconds_old: int):
		to_republish = filter(lambda t: t[1] > seconds_old, self.content_stats())
		repub_keys = list(map(operator.itemgetter(0), to_republish))
		repub_data = [self.load_data(k) for k in repub_keys]
		return zip(repub_keys, repub_data)

	@pre_prune()
	def __iter__(self):
		ikeys = self.contents()
		ivalues = [self.load_data(k) for k in ikeys]
		return zip(ikeys, ivalues)

	def __contains__(self, key: int) -> bool:
		return str(key) in self.contents()

	def __repr__(self):
		self.prune()
		return repr(self.contents())

	@pre_prune()
	def __len__(self):
		return len(self.contents())
