import sys
import os

__version__ = "2.3.1"

WORKDIR = os.path.basename(os.path.basename(os.path.abspath(__file__)))
if not WORKDIR in sys.path:
	sys.path.insert(0, WORKDIR)

if sys.version_info.major < 3 or sys.version_info.minor < 7:
	raise RuntimeError("Python version >= 3.7 required")
