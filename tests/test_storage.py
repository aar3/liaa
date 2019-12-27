import os

from kademlia.storage import EphemeralStorage, DiskStorage
from kademlia.node import NodeType
from kademlia.config import CONFIG


class TestEphemeralStorage:
	# pylint: disable=no-self-use
	def test__setitem__works_ok(self):
		storage = EphemeralStorage(10)
		storage['one'] = 'two'
		assert storage['one'] == 'two'

	def test_resource_expires_per_expiry(self):
		# Expiry time of 0 should force the prune to make all items stale
		# immediately
		storage = EphemeralStorage(0)
		storage['one'] = 'two'
		assert storage.get('one') is None

	def test_iter(self):
		storage = EphemeralStorage(10)
		storage['one'] = 'two'
		for key, value in storage:
			assert key == 'one'
			assert value == 'two'

	def test_iter_older_than(self):
		storage = EphemeralStorage(10)
		storage['one'] = 'two'
		for key, value in storage.iter_older_than(0):
			assert key == 'one'
			assert value == 'two'


class TestDiskStorage:

	def test_instantiation(self, mknode):
		node = mknode()
		storage = DiskStorage(node=node)

		assert isinstance(storage, DiskStorage)
		assert len(storage.contents()) == 0

	def test_persist_dir_exists(self, mknode):
		node = mknode()
		storage = DiskStorage(node=node)

		# have to call config's getter to instantiate dir
		assert os.path.exists(CONFIG.persist_dir)
		assert os.path.exists(storage.dir)

	def test_can_set_and_retrieve_basic_resource(self, mknode):
		node = mknode()
		storage = DiskStorage(node=node)
		resource = mknode()
		resource.type = NodeType.Resource
		resource.value = b"123"

		storage.set(resource)

		result = storage.get(resource.long_id)
		assert result == resource
