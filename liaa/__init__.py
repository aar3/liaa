import sys

__version__ = "2.3.1"

if sys.version_info.major < 3 or sys.version_info.minor < 7:
	raise RuntimeError("Python version >= 3.7 required")
