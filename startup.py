# -*- coding: utf-8 -*-
"""
AVRO extension startup.

Executed before ribbon UI is built on every pyRevit load/reload
(``sessionmgr._new_session``, before ``update_pyrevit_ui``).
"""
from __future__ import print_function

import os
import sys

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)


def _log_startup_error(ex):
    try:
        import config
        config._log(u"startup: {}".format(ex))
    except Exception:
        pass


try:
    import reload_fixup
    reload_fixup.prepare_ribbon_for_pyrevit_update()
    reload_fixup.schedule_post_load_ribbon_i18n()
except Exception as ex:
    _log_startup_error(ex)
