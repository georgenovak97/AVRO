# -*- coding: utf-8 -*-
"""Apply saved UI language to ribbon when pyRevit loads the extension."""
from __future__ import print_function

import os
import sys

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

try:
    import i18n
    import ribbon_i18n
    i18n.init_from_config()
    ribbon_i18n.init_from_config()
except Exception:
    pass
