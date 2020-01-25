
import functools
import logging
import operator
import os
import pickle
import time
from collections import OrderedDict
from itertools import takewhile

from liaa.node import ResourceNode

log = logging.getLogger(__name__)  # pylint: disable=invalid-name


def pre_prune():
	"""
	Decorator (syntactic sugar) for a storage interface's prune() method
	"""
	def wrapper(func):
		@functools.wraps(func)
		def _pre_prune(*args, **kwargs):
			"""
			Parameters
			----------
				args[0]: IStorage
					Reference to instance of storae interface
			"""
			log.debug("%s pruning items...", args[0].node)
			args[0].prune()
			return func(*args, **kwargs)
		return _pre_prune
	return wrapper


class IStorage:
	"""
	Base storage interface

	Parameters
	----------
		node: PeerNode
			The node representing this peer
		ttl: int
			Max age that items can live untouched before being pruned
			(default=604800 seconds = 1 week)
	"""
	def __init__(self, node, ttl=604800):
		self.node = node
		self.ttl = ttl
		self.root_dir = os.path.join(os.path.expanduser("~"), ".liaa")
		if not os.path.exists(self.root_dir):
			log.debug("Liaa dir at %s not found, creating...", self.root_dir)
			os.mkdir(self.root_dir)

		self.dir = os.path.join(self.root_dir, str(self.node.long_id))
		if not os.path.exists(self.dir):
			log.debug("Node dir at %s not found, creating...", self.dir)
			os.mkdir(self.dir)

	def prune(self):
		""" Prune storage interface """
		items = self.iter_older_than(self.ttl)
		log.debug("%s pruning 0 items older than %i", self.node, self.ttl)
		for key, _ in items:
			self.remove(key)

	def iter_older_than(self, seconds_old):
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
		matches = takewhile(lambda r: min_birthday >= r[2], zipped)
		items = list(map(operator.itemgetter(0, 1), matches))
		log.debug("%s returning %i nodes via iter_older_than=%i", self.node, len(items), seconds_old)
		return items

	def remove(self, key):
		raise NotImplementedError

	def _triple_iter(self):
		raise NotImplementedError


class EphemeralStorage(IStorage):
	def __init__(self, node, ttl=604800):
		"""
		EphemeralStorage

		Parameters
		----------
			node: PeerNode
				The node representing this peer
		"""
		super(EphemeralStorage, self).__init__(node, ttl)
		self.data = OrderedDict()

	@pre_prune()
	def get(self, key):
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
			Optional[ResourceNode]:
				Node if node is in storage, else `default`
		"""
		log.debug("%s fetching Node %s", self.node, key)
		if key in self:
			_, value = self.data[key]
			return ResourceNode(key, value)
		log.debug("Node %s not found on node %s", key, self.node)
		return None

	def set(self, node):
		"""
		Save a given Node in storage

		Parameters
		----------
			node: ResourceNode
				Node to be saved
		"""
		log.debug("%s setting node %s", self.node, node.key)
		if node in self:
			self.remove(node.key)
		self.data[node.key] = (time.monotonic(), node.value)
		log.debug("%s storage has %i items", self.node, len(self))

	def remove(self, key):
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

	def _triple_iter(self):
		"""
		Iterate over storage to return each contents key, time, and values
		"""
		ikeys = self.data.keys()
		ibirthday = map(operator.itemgetter(0), self.data.values())
		ivalues = map(operator.itemgetter(1), self.data.values())
		return zip(ikeys, ivalues, ibirthday)

	@pre_prune()
	def __iter__(self):
		log.debug("%s iterating over %i items in storage", self.node, len(self.data))
		items = self._triple_iter()
		nodes = [ResourceNode(*item) for item in items]

		for node in nodes:
			yield node

	def __contains__(self, key):
		return key in self.data

	def __len__(self):
		return len(self.data)


class DiskStorage(IStorage):
	def __init__(self, node, ttl=604800):
		"""
		Interface for disk storage

		Parameters
		----------
			node: ResourceNode
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
	def get(self, key):
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
			birthday, value = self._load_data(key)
			return ResourceNode(key, value, birthday)
		log.debug("Node %s not found on node %s", key, self.node)
		return None

	def set(self, node):
		"""
		Save a given Node in storage

		Parameters
		----------
			node: PeerNode
				Node to be saved
		"""
		if node.key in self:
			self.remove(node.key)
		log.debug("%s setting node %s", self.node, node.key)
		self._persist_data(time.monotonic(), node)
		log.debug("%s storage has %i items", self.node, len(self))

	def remove(self, key):
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

	def _triple_iter(self):
		"""
		Iterate over storage to return each contents key, time, and values
		"""
		items = [self._load_data(k) for k in self.contents()]
		bdays = [item[0] for item in items]
		values = [item[1] for item in items]
		return zip(self.contents(), values, bdays)


	def contents(self):
		"""
		List all nodes in storage

		Returns
		-------
			List[str]:
				Contents of storage directory
		"""
		return os.listdir(self.content_dir)

	def _persist_data(self, birthday, node):
		"""
		Save a given node's value to disk

		Parameters
		----------
			birthday: float
				time.monotonic() when savind item
			node: ResourceNode
				The node to save
		"""
		fname = os.path.join(self.content_dir, node.key)
		log.debug("%s attempting to persist %s", self.node, node.key)
		data = {"value": node.value, "time": birthday}
		with open(fname, "wb") as ctx:
			pickle.dump(data, ctx)

	def _load_data(self, key):
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
				return (data["time"], data["value"])
		except FileNotFoundError as err:
			log.error("%s could not load key at %s: %s", self.node, key, str(err))

	@pre_prune()
	def __iter__(self):
		log.debug("%s iterating over %i items in storage", self.node, len(self.contents()))
		items = self._triple_iter()
		nodes = [ResourceNode(*item) for item in items]
		for node in nodes:
			yield node

	def __contains__(self, key):
		return key in self.contents()

	def __len__(self):
		return len(self.contents())


StorageIface = EphemeralStorage
