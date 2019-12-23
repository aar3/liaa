"""
General catchall for functions that don't make sense as methods.
"""
import hashlib
import operator
import asyncio


class Sandbox:
	def __init__(self, obj):
		self.obj = obj
		self.mem = {}

	def stub(self, funcname, func):
		self.mem[funcname] = getattr(self.obj, funcname)
		setattr(self.obj, funcname, func)

	def restore(self):
		for funcname, func in self.mem.items():
			setattr(self.obj, funcname, func)


async def gather_dict(dic):
	cors = list(dic.values())
	results = await asyncio.gather(*cors)
	return dict(zip(dic.keys(), results))


def digest(string):
	if not isinstance(string, bytes):
		string = str(string).encode('utf8')
	return hashlib.sha1(string).digest()


def shared_prefix(args):
	"""
	Find the shared prefix between the strings.

	For instance:

		sharedPrefix(['blahblah', 'blahwhat'])

	returns 'blah'.
	"""
	i = 0
	while i < min(map(len, args)):
		if len(set(map(operator.itemgetter(i), args))) != 1:
			break
		i += 1
	return args[0][:i]


def bytes_to_bit_string(bites):
	bits = [bin(bite)[2:].rjust(8, '0') for bite in bites]
	return "".join(bits)


def hex_to_base_int(hx, base=16):
	return int(hx, base)
