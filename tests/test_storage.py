import os
import time

from liaa.storage import EphemeralStorage, DiskStorage
from liaa.node import Node, NodeType


class TestEphemeralStorage:
	# pylint: disable=no-self-use
	def test_can_instantiate_storage(self, mkpeer):
		storage = EphemeralStorage(mkpeer(), 10)
		assert isinstance(storage, EphemeralStorage)

	def test_can_set_and_get(self, mkpeer, mkresource):
		storage = EphemeralStorage(mkpeer(), 10)
		resource = mkresource(key="one", value=b"two")
		storage.set(resource)

		node = storage.get(resource.key)
		assert  node.value == b"two"

	def test_resource_expires_per_expiry(self, mkpeer, mkresource):
		# Expiry time of 0 should force the prune to make all items stale immediately
		storage = EphemeralStorage(mkpeer(), 0)
		resource = mkresource(key="one", value=b"two")
		storage.set(resource)
		assert not storage.get(resource.key)

	def test_iter(self, mkpeer, mkresource):
		storage = EphemeralStorage(mkpeer(), 0)
		resource = mkresource(key="one", value=b"two")
		storage.set(resource)
		for node in storage:
			assert node.key == resource.key
			assert node.value == resource.value

	def test_iter_older_than_returns_proper_keys_for_republishing(self, mkpeer, mkresource):
		storage = EphemeralStorage(mkpeer(), 0)
		resources = [mkresource(), mkresource()]

		for node in resources:
			storage.set(node)

		for key, value in storage.iter_older_than(0):
			node = mkresource(key, value)
			assert node in resources


class TestDiskStorage:

	# pylint: disable=no-self-use
	def test_instantiation(self, mkpeer):
		node = mkpeer()
		storage = DiskStorage(node)
		assert isinstance(storage, DiskStorage)
		assert len(storage) == 0

	def test_store_contents(self, mkpeer, mkresource):
		node = mkpeer()
		storage = DiskStorage(node)

		resource = mkresource()
		storage.set(resource)

		assert len(storage) == len(storage.contents()) == 1
		assert storage.contents()[0] == str(resource.key)

	def test_storage_remove(self, mkpeer, mkresource):
		node = mkpeer()
		storage = DiskStorage(node)

		resource = mkresource()
		storage.set(resource)

		assert len(storage) == 1

		storage.remove(resource.key)
		assert len(storage) == 0

	def test_load_data_returns_proper_payload(self, mkpeer, mkresource):
		node = mkpeer()
		storage = DiskStorage(node)

		resource = mkresource()
		storage.set(resource)

		# pylint: disable=protected-access
		data = storage._load_data(resource.key)
		assert resource.value == data

	def test_persist_dir_exists(self, mkpeer):
		node = mkpeer()
		storage = DiskStorage(node)

		assert os.path.exists(storage.dir)
		assert os.path.exists(storage.content_dir)

	def test_can_set_and_retrieve_basic_resource(self, mkpeer, mkresource):
		node = mkpeer()
		storage = DiskStorage(node)
		resource = mkresource()

		storage.set(resource)

		result = storage.get(resource.key)
		assert result == resource


	def test_prune_removes_old_data(self, mkpeer, mkresource):

		ttl = 3
		node = mkpeer()
		storage = DiskStorage(node, ttl=ttl)

		resources = [mkresource() for _ in range(3)]

		storage.set(resources[0])

		time.sleep(ttl + 2)

		storage.set(resources[1])

		assert len(storage) == 1

		for node in storage:
			assert node.key == resources[1].key
			assert node.value == resources[1].value
