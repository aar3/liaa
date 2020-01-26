import operator
import random
import string
import struct
import os
import ssl
import asyncio

from liaa import BASE_INT, MAX_KEYSIZE, MAX_LONG, BYTE_ORDER


def join_addr(addr):
	"""
	Join a tuple address to string
	"""
	return ":".join(map(str, addr))


def split_addr(addr):
	"""
	Split a string address to tuple
	"""
	host, port = addr.split(":")
	return host, int(port)


def rand_str(num=MAX_KEYSIZE):
	"""
	Create a random string array
	"""
	chars = string.ascii_letters + string.digits
	return "".join([random.choice(chars) for _ in range(num)])


def rand_int_id():
	"""
	Create a random string array
	"""
	return random.randint(1, MAX_LONG)


def int_to_hex(num: int):
	"""
	Convert an integer to hexidecimal format
	"""
	return int_to_digest(num).hex()


async def gather_dict(dic):
	"""
	Execute a list of coroutines and return the results in a hashmap
	"""
	cors = list(dic.values())
	results = await asyncio.gather(*cors)
	return dict(zip(dic.keys(), results))


def int_to_digest(num):
	"""
	Convert base integer to bytes
	"""
	return num.to_bytes(BASE_INT, byteorder='big')


def shared_prefix(args):
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


def bytes_to_bit_string(arr):
	"""
	Convert a byte array to a bit array
	"""
	bits = [bin(bite)[2:].rjust(8, '0') for bite in arr]
	return "".join(bits)


def hex_to_int(hexstr):
	"""
	Convert given hex to a base-BASE_INT integer
	"""
	return int(hexstr, BASE_INT)


def check_dht_value_type(value):
	"""
	Checks to see if the type of the value is a valid type for
	placing in the dht.
	"""
	typeset = [int, float, bool, str, bytes]
	return any(map(lambda t: isinstance(value, t), typeset))


def pack(arr, fmt=BYTE_ORDER):
	"""
	Pack a string into a byte array
	"""
	arr = arr.encode()
	return struct.pack(fmt, len(arr)) + arr


def unpack(arr, fmt=BYTE_ORDER):
	"""
	Unpack a byte array according to a given format
	"""
	size = struct.calcsize(fmt)
	return struct.unpack(fmt, arr[:size]), arr[size:]



def reverse_hex(number: int, base: int = BASE_INT):
	""" Used to reverse a long int back to its hexidecimal format """
	def digit_to_char(digit):
		if digit < 10:
			return str(digit)
		return chr(ord('a') + digit - 10)

	def _reverse_hex(number: int, base: int):
		if number < 0:
			return '-' + _reverse_hex(-number, base)
		# pylint: disable=invalid-name
		(d, m) = divmod(number, base)
		if d > 0:
			return _reverse_hex(d, base) + digit_to_char(m)
		return digit_to_char(m)

	return  _reverse_hex(number, base)


def long_to_key(number):
	""" Convert a long int back to its digest format """
	return unpack(bytes.fromhex(reverse_hex(number)))


def load_ssl(cert, key):
	"""
	Create and return an SSL context used for examples/tests/debugging
	"""
	if (not cert and not key) or (not os.path.exists(cert) or not os.path.exists(key)):
		return None
	ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
	ssl_ctx.load_cert_chain(cert, key)
	return ssl_ctx
