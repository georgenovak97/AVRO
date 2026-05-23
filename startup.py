# -*- coding: utf-8 -*-
"""
AVRO extension startup (runs on every pyRevit Reload).

Runs before pyRevit builds ribbon UI: restores tab/panel keys pyRevit expects,
then schedules button label localization after Reload completes.
"""
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

try:
    import reload_fixup
    reload_fixup.prepare_ribbon_for_pyrevit_update()
    reload_fixup.schedule_after_reload()
except Exception:
    pass
