import os
import time

from liaa.storage import EphemeralStorage, DiskStorage


class TestEphemeralStorage:
	# pylint: disable=no-self-use
	def test_can_instantiate_storage(self, mknode):
		storage = EphemeralStorage(mknode(), 10)
		assert isinstance(storage, EphemeralStorage)

	def test_can_set_and_get(self, mknode, mkrsrc):
		storage = EphemeralStorage(mknode(), 10)
		resource = mkrsrc(key=b"one", value=b"two")
		storage.set(resource)

		node = storage.get(resource.hex)
		assert  node.value == b"two"

	def test_resource_expires_per_expiry(self, mknode, mkrsrc):
		# Expiry time of 0 should force the prune to make all items stale immediately
		storage = EphemeralStorage(mknode(), 0)
		resource = mkrsrc(key=b"one", value=b"two")
		storage.set(resource)
		assert not storage.get(resource.hex)

	def test_iter(self, mknode, mkrsrc):
		storage = EphemeralStorage(mknode(), 0)
		resource = mkrsrc(key=b"one", value=b"two")
		storage.set(resource)
		for node in storage:
			assert node.hex == resource.hex
			assert node.value == resource.value

	def test_iter_older_than_returns_proper_keys_for_republishing(self, mknode, mkrsrc):
		storage = EphemeralStorage(mknode(), 0)
		resource = mkrsrc(key=b"one", value=b"two")
		storage.set(resource)
		for key, value in storage.iter_older_than(0):
			assert key == resource.hex
			assert value == resource.value


class TestDiskStorage:

	# pylint: disable=no-self-use
	def test_instantiation(self, mknode):
		node = mknode()
		storage = DiskStorage(node)

		assert isinstance(storage, DiskStorage)
		assert len(storage) == 0

	def test_store_contents(self, mknode, mkrsrc):
		node = mknode()
		storage = DiskStorage(node)

		resource = mkrsrc()
		storage.set(resource)

		assert len(storage) == len(storage.contents()) == 1
		assert storage.contents()[0] == str(resource.hex)

	def test_remove_works_ok(self, mknode, mkrsrc):
		node = mknode()
		storage = DiskStorage(node)

		resource = mkrsrc()
		storage.set(resource)

		assert len(storage) == 1

		storage.remove(resource.hex)
		assert len(storage) == 0

	def test_load_data_returns_proper_payload(self, mknode, mkrsrc):
		node = mknode()
		storage = DiskStorage(node)

		resource = mkrsrc()
		storage.set(resource)

		# pylint: disable=protected-access
		data = storage._load_data(resource.hex)
		assert resource.value == data

	def test_persist_dir_exists(self, mknode):
		node = mknode()
		storage = DiskStorage(node)

		assert os.path.exists(storage.dir)
		assert os.path.exists(storage.content_dir)

	def test_can_set_and_retrieve_basic_resource(self, mknode, mkrsrc):
		node = mknode()
		storage = DiskStorage(node)
		resource = mkrsrc()

		storage.set(resource)

		result = storage.get(resource.hex)
		assert result == resource


	def test_prune_removes_old_data(self, mknode, mkrsrc):
		node = mknode()

		# instantiate disk storage with 5 seconds ttl
		storage = DiskStorage(node, ttl=3)

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

		for node in storage:
			assert node.hex == r2.hex
			assert node.value == r2.value
