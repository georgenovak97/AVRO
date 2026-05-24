# -*- coding: utf-8 -*-
"""Hide AVRO tab immediately when user clicks pyRevit Reload or Update."""
from __future__ import print_function

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIB = os.path.join(_ROOT, "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)


def _command_name():
    try:
        from pyrevit import EXEC_PARAMS
        return getattr(EXEC_PARAMS, "command_name", None)
    except Exception:
        return None


try:
    import reload_fixup
    if reload_fixup.is_reload_or_update_command(_command_name()):
        reload_fixup.hide_avro_tab()
except Exception:
    pass
