import hashlib

from kademlia.utils import (digest, shared_prefix, hex_to_base_int)


class TestUtils:
	def test_digest(self):  # pylint: disable=no-self-use
		dig = hashlib.sha1(b'1').digest()
		assert dig == digest(1)

		dig = hashlib.sha1(b'another').digest()
		assert dig == digest('another')

	def test_shared_prefix(self):  # pylint: disable=no-self-use
		args = ['prefix', 'prefixasdf', 'prefix', 'prefixxxx']
		assert shared_prefix(args) == 'prefix'

		args = ['p', 'prefixasdf', 'prefix', 'prefixxxx']
		assert shared_prefix(args) == 'p'

		args = ['one', 'two']
		assert shared_prefix(args) == ''

		args = ['hi']
		assert shared_prefix(args) == 'hi'

	def test_to_base16_int(self):  # pylint: disable=no-self-use
		num = 5
		num_as_bytes = bytes([num])
		assert hex_to_base_int(num_as_bytes.hex()) == num
