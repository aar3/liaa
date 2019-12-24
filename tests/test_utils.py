import hashlib
import asyncio

# pylint: disable=bad-continuation
from kademlia.utils import (
	digest,
	shared_prefix,
	bytes_to_bit_string,
	hex_to_base_int,
	check_dht_value_type,
	gather_dict
)


class TestUtils:
	# pylint: disable=no-self-use
	def test_digest(self):
		dig = hashlib.sha1(b'1').digest()
		assert dig == digest(1)

		dig = hashlib.sha1(b'another').digest()
		assert dig == digest('another')

	def test_shared_prefix(self):
		args = ['prefix', 'prefixasdf', 'prefix', 'prefixxxx']
		assert shared_prefix(args) == 'prefix'

		args = ['p', 'prefixasdf', 'prefix', 'prefixxxx']
		assert shared_prefix(args) == 'p'

		args = ['one', 'two']
		assert shared_prefix(args) == ''

		args = ['hi']
		assert shared_prefix(args) == 'hi'

	def test_bytes_to_bit_string(self):
		arr = b"hello world"
		bstr = [bin(bite)[2:].rjust(8, '0') for bite in arr]
		assert "".join(bstr) == bytes_to_bit_string(arr)

	def test_to_base16_int(self):
		num = 5
		num_as_bytes = bytes([num])
		assert hex_to_base_int(num_as_bytes.hex()) == num

	def test_check_dht_value_type_returns_true_when_arg_is_valid(self):
		# pylint: disable=invalid-name
		a = check_dht_value_type("foo")
		assert a

		b = check_dht_value_type(8)
		assert b

		c = check_dht_value_type(b'123')
		assert c

		d = check_dht_value_type(True)
		assert d

		e = check_dht_value_type(3.14)
		assert e

		f = check_dht_value_type({})
		assert not f

		g = check_dht_value_type([])
		assert not g

		# pylint: disable=too-few-public-methods
		class Foo:
			pass

		h = check_dht_value_type(Foo())
		assert not h

	def test_gather_dict(self):
		coros = [asyncio.sleep(1) for _ in range(3)]
		keys = [str(i) for i in range(3)]
		coros = dict(zip(keys, coros))

		loop = asyncio.new_event_loop()
		results = loop.run_until_complete(gather_dict(coros))
		assert isinstance(results, dict)
		assert len(results) == 3

		assert all(map(lambda p: not p[1], results.items()))
