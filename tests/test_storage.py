import os
import time

from kademlia.storage import EphemeralStorage, DiskStorage
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

	# pylint: disable=no-self-use
	def test_instantiation(self, mknode):
		node = mknode()
		storage = DiskStorage(node=node)

		assert isinstance(storage, DiskStorage)
		assert len(storage) == 0

	def test_store_contents(self, mknode, mkrsrc):
		node = mknode()
		storage = DiskStorage(node=node)

		resource = mkrsrc()
		storage.set(resource)

		assert len(storage) == len(storage.contents()) == 1
		assert storage.contents()[0] == str(resource.long_id)

	def test_remove_works_ok(self, mknode, mkrsrc):
		node = mknode()
		storage = DiskStorage(node=node)

		resource = mkrsrc()
		storage.set(resource)

		assert len(storage) == 1

		storage.remove(resource.long_id)
		assert len(storage) == 0

	def test_load_data_returns_proper_payload(self, mknode, mkrsrc):
		node = mknode()
		storage = DiskStorage(node=node)

		resource = mkrsrc()
		storage.set(resource)

		data = storage.load_data(resource.long_id)
		assert resource.value == data

	def test_persist_dir_exists(self, mknode):
		node = mknode()
		storage = DiskStorage(node=node)

		# have to call config's getter to instantiate dir
		assert os.path.exists(CONFIG.persist_dir)
		assert os.path.exists(storage.dir)

	def test_can_set_and_retrieve_basic_resource(self, mknode, mkrsrc):
		node = mknode()
		storage = DiskStorage(node=node)
		resource = mkrsrc()

		storage.set(resource)

		result = storage.get(resource.long_id)
		assert result == resource


	def test_prune_removes_old_data(self, mknode, mkrsrc):
		node = mknode()

		# instantiate disk storage with 5 seconds ttl
		storage = DiskStorage(node=node, ttl=3)

		# create some resources
		# pylint: disable=invalid-name
		r1 = mkrsrc()
		r2 = mkrsrc()

		# set our first node
		storage.set(r1)

		# sleep over 3 seconds
		time.sleep(4)

		# our next call to set will call storage.prune thus removing r1
		storage.set(r2)

		# we should only have r2
		assert len(storage) == 1

		for key, value in storage:
			assert int(key) == r2.long_id
			assert value == r2.value
