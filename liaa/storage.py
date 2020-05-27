import logging
import operator
import abc
import os
import time
from collections import OrderedDict
from itertools import takewhile
from typing import List, Any, Tuple, Iterator, Optional, Dict

from liaa.node import IndexNode, Node, PingNode


log = logging.getLogger(__name__)


class BaseStorage(abc.ABC):
    """
	Base storage interface

	Parameters
	----------
		node: PingNode
			The node representing this peer
		ttl: int
			Max age that items can live untouched before being pruned
			(default=604800 seconds = 1 week)
	"""

    def __init__(self, node: PingNode, ttl: int = 604800):
        self.node = node
        self.ttl = ttl
        self.root_dir = os.path.join(os.path.expanduser("~"), ".liaa")

        self._init_rootdir()

    def _init_rootdir(self):
        if not os.path.exists(self.root_dir):
            log.debug("liaa dir at %s not found, creating...", self.root_dir)
            os.mkdir(self.root_dir)

        self.dir = os.path.join(self.root_dir, str(self.node.long_id))

        if not os.path.exists(self.dir):
            log.debug("node dir at %s not found, creating...", self.dir)
            os.mkdir(self.dir)

    def prune(self):
        """ Prune storage interface """
        items = self.iter_older_than(self.ttl)
        log.debug("%s pruning 0 items older than %i", self.node, self.ttl)
        for node in items:
            self.remove(node)

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
        items = list(map(operator.itemgetter(1), self._triple_iter()))
        matches = takewhile(lambda node: min_birthday >= node.birthday, items)

        log.debug(
            "%s returning %i nodes via iter_older_than=%i",
            self.node,
            len(items),
            seconds_old,
        )
        return list(matches)

    @abc.abstractmethod
    def get(self, key: str, default: Optional[IndexNode]) -> Optional[IndexNode]:
        raise NotImplementedError

    @abc.abstractmethod
    def set(self, node: IndexNode):
        raise NotImplementedError

    @abc.abstractmethod
    def remove(self, node: IndexNode):
        raise NotImplementedError

    @abc.abstractmethod
    def _triple_iter(self):
        raise NotImplementedError


class EphemeralStorage(BaseStorage):
    def __init__(self, node: PingNode, ttl: int = 604800):
        """
		EphemeralStorage

		Parameters
		----------
			node: Node
				The node representing this peer
		"""
        super(EphemeralStorage, self).__init__(node, ttl)
        self.data: Dict[str, IndexNode] = OrderedDict()

    def get(
        self, key: str, default: Optional[IndexNode] = None
    ) -> Optional[IndexNode]:
        """
		Retrieve a node from storage

		Parameters
		----------
			key: str
				Key of node to be fetched
			default: Optional[Any]
				Default value to return if node not in storage

		Return
		-------
			Optional[IndexNode]:
				Node if node is in storage, else `default`
		"""
        self.prune()
        log.debug("%s fetching Node %i", self.node, key)
        return self.data.get(key, default)

    def set(self, node: IndexNode):
        """
		Save a given Node in storage

		Parameters
		----------
			node: IndexNode
				Node to be saved
		"""
        log.debug("%s setting node %s", self.node, node.long_id)
        if node in self:
            self.remove(node)
        node.birthday = time.monotonic()
        self.data[node.key] = node
        log.debug("%s storage has %i items", self.node, len(self))

    def remove(self, node: Node):
        """
		Remove a node from storage

		Parameters
		----------
			node: Node
				Node to be removed
		"""
        log.debug("%s removing resource %s", self.node, node)
        if node in self:
            del self.data[node.key]

    def _triple_iter(self) -> List[Tuple[str, IndexNode]]:
        """
		Iterate over storage to return each contents key, time, and values
		"""
        return list(self.data.items())

    def __iter__(self) -> Iterator[Node]:
        self.prune()
        log.debug("%s iterating over %i items in storage", self.node, len(self.data))
        items = self._triple_iter()

        for _, node in items:
            yield node

    def __contains__(self, node: Node) -> bool:
        return node.key in self.data

    def __len__(self) -> int:
        return len(self.data)
