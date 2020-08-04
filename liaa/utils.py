import operator
import random
import string
import struct
import asyncio
from _typing import *


from liaa import BASE_INT, MAX_KEYSIZE, MAX_LONG, BYTE_ORDER


def join_addr(addr: Tuple[str, Union[int, str]]) -> str:
    """
	Join a tuple address to string
	"""
    return ":".join(map(str, addr))


def split_addr(addr: str) -> IPv4:
    """
	Split a string address to tuple
	"""
    host, port = addr.split(":")
    return host, int(port)


def rand_str(num: int = MAX_KEYSIZE) -> str:
    """
	Create a random string array
	"""
    chars = string.ascii_letters + string.digits
    return "".join([random.choice(chars) for _ in range(num)])


def rand_int_id() -> int:
    """
	Create a random string array
	"""
    return random.randint(1, MAX_LONG)


async def gather_dict(dic: Dict[str, Awaitable[T]]) -> Dict[str, T]:
    """
	Execute a list of coroutines and return the results in a hashmap
	"""
    cors = list(dic.values())
    results = await asyncio.gather(*cors)
    return dict(zip(dic.keys(), results))


def shared_prefix(args: List[str]) -> str:
    """
	Find the shared prefix between the strings.
	"""
    i = 0
    while i < min(map(len, args)):
        if len(set(map(operator.itemgetter(i), args))) != 1:
            break
        i += 1
    return args[0][:i]


def bytes_to_bits(arr: bytes) -> str:
    """
	Convert a byte array to a bit array
	"""
    bits = [bin(bite)[2:].rjust(8, "0") for bite in arr]
    return "".join(bits)


def hex_to_int(hexstr: str) -> int:
    """
	Convert given hex to a base-BASE_INT integer
	"""
    return int(hexstr, BASE_INT)


def check_dht_value_type(value: T) -> bool:
    """
	Checks to see if the type of the value is a valid type for
	placing in the dht.
	"""
    typeset = [int, float, bool, str, bytes]
    return any(map(lambda t: isinstance(value, t), typeset))


def pack(s: str, fmt: str = BYTE_ORDER) -> bytes:
    """
	Pack a string into a byte array
	"""
    b: bytes = s.encode()
    return struct.pack(fmt, len(b)) + b


def unpack(b: bytes, fmt: str = BYTE_ORDER) -> Tuple[Tuple[Any, ...], bytes]:
    """
	Unpack a byte array according to a given format
	"""
    size = struct.calcsize(fmt)
    return struct.unpack(fmt, b[:size]), b[size:]


def reverse_hex(number: int, base: int = BASE_INT) -> str:
    """ Used to reverse a long int back to its hexidecimal format """

    def digit_to_char(digit: int) -> str:
        if digit < 10:
            return str(digit)
        return chr(ord("a") + digit - 10)

    def _reverse_hex(number: int, base: int) -> str:
        if number < 0:
            return "-" + _reverse_hex(-number, base)

        (d, m) = divmod(number, base)
        if d > 0:
            return _reverse_hex(d, base) + digit_to_char(m)
        return digit_to_char(m)

    return _reverse_hex(number, base)


def long_to_key(number: int) -> Tuple[Tuple[Any, ...], bytes]:
    """ Convert a long int back to its digest format """
    return unpack(bytes.fromhex(reverse_hex(number)))
