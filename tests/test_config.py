from kademlia.config import CONFIG


# pylint: disable=too-few-public-methods
class TestConfig:
	# pylint: disable=no-self-use
	def test_can_load_config(self):

		assert CONFIG.alpha == 3
		assert CONFIG.ksize == 20
		assert CONFIG.interface == "0.0.0.0"
	