# -*- coding: utf-8 -*-
"""Open Search from the current AVRO Tools panel."""
from __future__ import print_function

import os
import sys

_LIB = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib")
)
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import search_integration


search_integration.show_search()
