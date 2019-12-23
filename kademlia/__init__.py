import sys

"""
Kademlia is a Python implementation of the Kademlia protocol which
utilizes the asyncio library.
"""
__version__ = "2.2"

if sys.version_info.major < 3 or sys.version_info.minor < 7:
	raise RuntimeError("Python version >= 3.7 required")
