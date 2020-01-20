import sys
import operator
import random
import string
import struct
import os
import ssl
import asyncio
from typing import Dict, Any, List, Union, Tuple, Optional

from liaa import BASE_INT, MAX_KEYSIZE, MAX_LONG, BYTE_ORDER


def join_addr(addr: Tuple[str, int]) -> str:
	"""
	Join a tuple address to string

	Parameters
	----------
		addr: Tuple[str, int]
			Address to be joined

	Returns
	-------
		str:
			String of address
	"""
	return ":".join(map(str, addr))


def split_addr(addr: "str") -> Tuple[str, int]:
	"""
	Split a string address to tuple

	Parameters
	----------
		addr: str
			Address to transform

	Returns
	-------
		Tuple[str, int]:
			Tuple version of input address
	"""
	host, port = addr.split(":")
	return host, int(port)


def rand_str(num: int = MAX_KEYSIZE) -> str:
	"""
	Create a random string array
	"""
	chars = string.ascii_letters + string.digits
	return "".join([random.choice(chars) for _ in range(num)])


def rand_int_id() -> str:
	"""
	Create a random string array

	Returns
	-------
		int:
			MAX_BITSIZE-bit integer
	"""
	return random.randint(1, MAX_LONG)

def rand_digest_id():
	num = rand_int_id()
	return int_to_digest(num)


def int_to_hex(num: int) -> str:
	return int_to_digest(num).hex()


async def gather_dict(dic: Dict[str, Any]) -> Dict[str, Any]:
	"""
	Execute a list of coroutines and return the results
	in a hashmap

	Parameters
	----------
		dic: Dict[str, Any]
			Hashmap of coroutines to be execute

	Returns
	-------
		Dict[str, Any]:
			Results of executed coroutines
	"""
	cors = list(dic.values())
	results = await asyncio.gather(*cors)
	return dict(zip(dic.keys(), results))


def digest_to_int(byte_arr: bytes) -> int:
	return hex_to_int(byte_arr.hex())


def int_to_digest(num: int) -> bytes:
	return num.to_bytes(BASE_INT, byteorder='big')


def shared_prefix(args: List[str]) -> str:
	"""
	Find the shared prefix between the strings.

	Parameters
	----------
		*args:
			Variable length

	Example
	-------
		assert 'blah' == shared_prefix(['blahblah', 'blahwhat'])
	"""
	i = 0
	while i < min(map(len, args)):
		if len(set(map(operator.itemgetter(i), args))) != 1:
			break
		i += 1
	return args[0][:i]


def bytes_to_bit_string(arr: bytes) -> str:
	"""
	Convert a byte array to a bit array

	Parameters
	----------
		arr: bytes
			Bytes to be transformed

	Returns
	-------
		str:
			bit array of input
	"""
	bits = [bin(bite)[2:].rjust(8, '0') for bite in arr]
	return "".join(bits)


def hex_to_int(hexstr: str) -> int:
	"""
	Convert given hex to a base-BASE_INT integer

	Parameters
	----------
		hexstr: bytes
			Hex byte array
		base: int
			Base of integer conversion (default=20)
	"""
	return int(hexstr, BASE_INT)


def check_dht_value_type(value: Any) -> bool:
	"""
	Checks to see if the type of the value is a valid type for
	placing in the dht.

	Parameters
	----------
		value: Any
			Value to be checked

	Returns
	-------
		bool:
			Indicating whether or not type is in DHT types
	"""
	# pylint: disable=bad-continuation
	typeset = [
		int,
		float,
		bool,
		str,
		bytes
	]
	return type(value) in typeset  # pylint: disable=unidiomatic-typecheck


class ArgsParser:
	def __init__(self):
		"""
		Util used to parse command line args on app start


		"""
		self._data: Dict[str, Union[str, int, bool]] = {}

	def add_many(self, opts: List[Tuple[str, str]]) -> None:
		"""
		Add command line args to ArgsParser.data

		Parameters
		-----------
			opts: List[Tuple[str, str]]
				List of tuple key,value pairs to add


		"""
		for key, val in opts:
			self._data[key] = val

	def get(self, key: str, alt_key: str) -> Optional[str]:
		"""
		Get a key from the ArgsParser, or get the alt_key if the key
		isnt present, else log and exit

		Parameters
		----------
			key: str
				First option key to fetch
			alt_key: str
				Second option key to fetch

		Returns
		-------
			Optional[str]:
				Value associated with key/alt_key
		"""
		try:
			return self._data[key]
		except KeyError:
			try:
				return self._data[alt_key]
			except KeyError:
				print(f"opt {key} {alt_key} not in args")
				sys.exit(1)

	def __contains__(self, key: str) -> bool:
		return key in self._data

	# pylint: disable=no-self-use
	def has_help_opt(self):
		return len(self._data) == 1 and "-h" in self._data or "--help" in self._data

	def has_proper_opts(self):
		# pylint: disable=bad-continuation
		required = [
			("-i", "--ip"),
			("-p", "--port"),
		]
		def has_arg(arg):
			return arg[0] in self._data or arg[1] in self._data
		return all(map(has_arg, required)), "missing required opts"


def str_arg_to_bool(arg: str) -> Union[bool, str]:
	"""
	Convert string cli arg to boolean

	Parameters
	----------
		arg: str
			Arg to be converted

	Returns
	-------
		Union[bool, str]:
			bool if arg is false else original arg
	"""
	return False if arg.lower() == 'false' else arg


def pack(arr: str, fmt: str = BYTE_ORDER) -> bytes:
	"""
	Pack a string into a byte array

	Parameters
	----------
		arr: str
			String array to pack
		fmt: str
			Pack style (default big Indian)
	"""
	arr = arr.encode()
	return struct.pack(fmt, len(arr)) + arr


def unpack(arr: bytes, fmt: str = BYTE_ORDER) -> Tuple[int, bytes]:
	"""
	Unpack a byte array according to a given format

	Parameters
	----------
		fmt: str
			Byte-order style (default big Indian)
	"""
	size = struct.calcsize(fmt)
	return struct.unpack(fmt, arr[:size]), arr[size:]


def digit_to_char(digit: int):
	if digit < 10:
		return str(digit)
	return chr(ord('a') + digit - 10)


def reverse_hex(number: int, base: int = BASE_INT) -> str:
	def _reverse_hex(number: int, base: int):
		if number < 0:
			return '-' + _reverse_hex(-number, base)
		# pylint: disable=invalid-name
		(d, m) = divmod(number, base)
		if d > 0:
			return _reverse_hex(d, base) + digit_to_char(m)
		return digit_to_char(m)
	return  _reverse_hex(number, base)


def long_to_key(number: int) -> str:
	return unpack(bytes.fromhex(reverse_hex(number)))


def debug_ssl_ctx(dirname: str) -> Optional[ssl.SSLContext]:
	"""
	Create and return an SSL context used for examples/tests/debugging

	Returns
	-------
		Optional[ssl.SSLContext]
	"""
	certfile = os.path.join(dirname, "pub.cert")
	keyfile = os.path.join(dirname, "priv.key")
	if not os.path.exists(certfile) or not os.path.exists(keyfile):
		return None
	ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
	ssl_ctx.load_cert_chain(certfile, keyfile)
	return ssl_ctx
