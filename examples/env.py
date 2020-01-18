"""
Python packaging hack to load our root dir into our $PYTHONPATH
"""

import os
import sys

ROOTDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not ROOTDIR in sys.path:
    sys.path.insert(0, ROOTDIR)
