from kademlia.config import Config

class TestConfig:
	# pylint: disable=no-self-use
	def test_can_load_config(self):
		cfg = Config()

		assert cfg.alpha == 3
		assert cfg.ksize == 20
		assert cfg.interface == "0.0.0.0"
