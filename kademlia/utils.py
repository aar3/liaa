"""
General catchall for functions that don't make sense as methods.
"""
import hashlib
import operator
import asyncio
from typing import Dict, Any, List, Union


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


def digest(arr: Union[str, bytes]) -> bytes:
	"""
	Return the SHA1 hash of a given string/byte array

	Parameters
	----------
		arr: Union[str, bytes]
			Byte/string array to be hashed

	Returns
	-------
		bytes:
			Hash of given byte/string array
	"""
	if not isinstance(arr, bytes):
		arr = str(arr).encode('utf8')
	return hashlib.sha1(arr).digest()


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


def hex_to_base_int(hexval: bytes, base=16) -> int:
	"""
	Convert given hex to a base-16 integer

	Parameters
	----------
		hexval: bytes
			Hex byte array
		base: int
			Base of integer conversion (default=16)
	"""
	return int(hexval, base)


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
