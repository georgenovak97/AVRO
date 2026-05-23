# -*- coding: utf-8 -*-
"""Load saved language into i18n after pyRevit session start (no ribbon changes here)."""
from __future__ import print_function

import os
import sys

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

try:
    import i18n
    i18n.init_from_config()
except Exception:
    pass
