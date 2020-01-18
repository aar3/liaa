import asyncio

from liaa import MAX_KEYSIZE, MAX_LONG, BASE_INT
# pylint: disable=bad-continuation
from liaa.utils import (
	shared_prefix,
	bytes_to_bit_string,
	hex_to_int,
	ArgsParser,
	check_dht_value_type,
	gather_dict,
	join_addr,
	split_addr,
	digest_to_int,
	rand_str,
	pack,
	rand_int_id,
	long_to_key,
	int_to_digest
)


class TestUtils:

	# pylint: disable=no-self-use
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

	def test_to_base20_int(self):
		num = 5
		num_as_bytes = bytes([num])
		assert hex_to_int(num_as_bytes.hex()) == num

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

	def test_join_addr(self):
		addr = ("0.0.0.0", 8000)
		assert join_addr(addr) == "0.0.0.0:8000"

	def test_split_addr(self):
		addr = "0.0.0.0:8000"
		assert split_addr(addr) == ("0.0.0.0", 8000)

	def test_rand_str(self):
		result = rand_str()
		assert isinstance(result, str)
		assert len(result) == MAX_KEYSIZE

	def test_rand_int_id(self):
		result = rand_int_id()
		assert isinstance(result, int)
		assert 0 < result < MAX_LONG

	def test_digest_to_int(self):
		num = 10
		byte_arr = num.to_bytes(20, byteorder='big')
		assert digest_to_int(byte_arr) == num

	def test_int_to_digest(self):
		num = 10
		byte_arr = num.to_bytes(BASE_INT, byteorder='big')
		assert byte_arr == int_to_digest(num)

	def test_long_to_key(self):
		key = rand_str(16)
		long = int(pack(key).hex(), BASE_INT)
		_, inverse = long_to_key(long)
		assert inverse.decode() == key

class TestArgsParser:

	# pylint: disable=no-self-use
	def test_can_set_and_get_via_primary_flag(self):
		parser = ArgsParser()
		opts = [("-f", "foo"), ("--bar", "bar"), ("-z", "1")]
		parser.add_many(opts)

		assert parser.get("-f", "--foo") == "foo"

	def test_can_set_and_get_via_secondary_flag(self):
		parser = ArgsParser()
		opts = [("--foo", "foo"), ("--bar", "bar"), ("-z", "1")]
		parser.add_many(opts)

		assert parser.get("-f", "--foo") == "foo"

	def test_has_help_opt_is_true(self):
		parser = ArgsParser()
		opts = [("-h", "")]
		parser.add_many(opts)
		assert parser.has_help_opt()
