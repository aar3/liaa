import os
import time

from liaa.storage import EphemeralStorage


class TestEphemeralStorage:
    def test_can_init_ephemeral_storage(self, make_network_node):
        storage = EphemeralStorage(make_network_node(), 10)
        assert isinstance(storage, EphemeralStorage)

    def test_root_dir_is_created_on_init(self, make_storage):
        storage = make_storage()
        assert os.path.exists(storage.root_dir) and os.path.isdir(storage.root_dir)

    def test_prune_removes_nodes_older_than_ttl_arg(
        self, make_storage, make_storage_node
    ):
        storage = make_storage(2)

        nodes = [make_storage_node() for _ in range(3)]
        for node in nodes:
            storage.set(node)

        time.sleep(2)
        storage.prune()

        assert not storage

    def test_can_set_and_get_storage_node(self, make_storage, make_storage_node):
        storage = make_storage(10)
        resource = make_storage_node(key="one", value=b"two")
        storage.set(resource)

        node = storage.get(resource.key)
        assert node == make_storage_node(key="one", value=b"two")

    def test_can_remove_storage_node(self, make_storage_node, make_storage):
        storage = make_storage()
        node = make_storage_node()
        storage.set(node)

        storage.remove(node)
        assert not storage

    def test_triple_iter_returns_all_storage_data(
        self, make_storage_node, make_storage
    ):
        storage = make_storage()
        nodes = [make_storage_node() for _ in range(3)]
        for node in nodes:
            storage.set(node)

        # pylint: disable=protected-access
        results = storage._triple_iter()
        assert isinstance(results, list)
        assert len(results) == 3
        assert isinstance(results[0], tuple)

    def test_iter_iterates_properly_over_triple_iter_return_value(
        self, make_storage, make_storage_node
    ):
        storage = make_storage()
        nodes = [make_storage_node() for _ in range(3)]
        for node in nodes:
            storage.set(node)

        for i, node in enumerate(storage):
            assert node.key == nodes[i].key

    def test_contains_returns_whether_or_not_node_exists_in_storage(
        self, make_storage, make_storage_node
    ):
        storage = make_storage()
        nodes = [make_storage_node() for _ in range(3)]
        for node in nodes:
            storage.set(node)

        assert nodes[0] in storage

        storage.remove(nodes[0])

        assert not nodes[0] in storage

    def test_storage_expires_evicts_resources_older_than_ttl(
        self, make_storage, make_storage_node
    ):
        storage = make_storage(0)
        resource = make_storage_node(key="one", value=b"two")
        storage.set(resource)
        assert not storage.get(resource.long_id)

    def test_iter_uses_nodes_in_storage_data(self, make_storage, make_storage_node):
        storage = make_storage(0)
        resource = make_storage_node(key="one", value=b"two")
        storage.set(resource)

        for node in storage:
            assert node.key == resource.key
            assert node.value == resource.value

    def test_iter_older_than_iters_nodes_older_than_ttl_arg(
        self, make_storage, make_storage_node
    ):
        storage = make_storage(5)
        resources = [make_storage_node() for _ in range(3)]

        for node in resources:
            storage.set(node)

        for key, value in storage.iter_older_than(3):
            node = make_storage_node(key, value)
            assert node in resources
