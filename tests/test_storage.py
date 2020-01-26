import os
import time

from liaa.storage import EphemeralStorage, DiskStorage


class TestEphemeralStorage:
	# pylint: disable=no-self-use
	def test_can_instantiate(self, mkpeer):
		storage = EphemeralStorage(mkpeer(), 10)
		assert isinstance(storage, EphemeralStorage)

	def test_set_and_get(self, mkpeer, mkresource):
		storage = EphemeralStorage(mkpeer(), 10)
		resource = mkresource(key="one", value=b"two")
		storage.set(resource)

		node = storage.get(resource.key)
		assert  node.value == b"two"

	def test_storage_ttl(self, mkpeer, mkresource):
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

	def test_iter_older_than(self, mkpeer, mkresource):
		storage = EphemeralStorage(mkpeer(), 5)
		resources = [mkresource() for _ in range(3)]

		for node in resources:
			storage.set(node)

		for key, value in storage.iter_older_than(3):
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

	def test_load_data(self, mkpeer, mkresource):
		storage = DiskStorage(mkpeer())
		resource = mkresource()
		storage.set(resource)

		# pylint: disable=protected-access
		(bday, value) = storage._load_data(resource.key)
		assert resource.value == value
		assert isinstance(bday, float)

	def test_persist_dir_exists(self, mkpeer):
		storage = DiskStorage(mkpeer())

		assert os.path.exists(storage.dir)
		assert os.path.exists(storage.content_dir)

	def test_set_and_get(self, mkpeer, mkresource):
		storage = DiskStorage(mkpeer())
		resource = mkresource()
		storage.set(resource)
		result = storage.get(resource.key)
		assert result == resource


	def test_prune_removes_old_data(self, mkpeer, mkresource):

		ttl = 3
		storage = DiskStorage(mkpeer(), ttl=ttl)
		resources = [mkresource() for _ in range(3)]
		storage.set(resources[0])

		time.sleep(ttl + 2)
		storage.prune()

		storage.set(resources[1])
		assert len(storage) == 1

		for node in storage:
			assert node.key == resources[1].key
			assert node.value == resources[1].value
