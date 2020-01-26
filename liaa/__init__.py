import sys
import os

__version__ = "1.1.5"

WORKDIR = os.path.basename(os.path.basename(os.path.abspath(__file__)))
if not WORKDIR in sys.path:
	sys.path.insert(0, WORKDIR)


MAX_BITSIZE = 200
MAX_LONG = 2**MAX_BITSIZE
BASE_INT = 20
MAX_KEYSIZE = 15
BYTE_ORDER = 'I'


if sys.version_info.major < 3 or sys.version_info.minor < 7:
	raise RuntimeError("Python version >= 3.7 required")
