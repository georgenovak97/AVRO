# -*- coding: utf-8 -*-
"""
Apply saved UI language after the AVRO ribbon is fully built.

Runs on ApplicationInitialized; defers ribbon updates until Idling so
pyRevit Reload does not leave a half-built tab (Settings only).
"""
from __future__ import print_function

import os
import sys

_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

_IDLE_HANDLER = None
_IDLE_TICKS = 0
_IDLE_MAX = 30


def _unregister_idling(uiapp):
    global _IDLE_HANDLER
    if uiapp is None or _IDLE_HANDLER is None:
        _IDLE_HANDLER = None
        return
    try:
        uiapp.Idling -= _IDLE_HANDLER
    except Exception:
        pass
    _IDLE_HANDLER = None


def _apply_ribbon_i18n(uiapp):
    try:
        import i18n
        import ribbon_i18n
        i18n.init_from_config()
        if ribbon_i18n.apply():
            _unregister_idling(uiapp)
            return True
    except Exception:
        pass
    return False


def _on_idling(sender, args):
    global _IDLE_TICKS
    _IDLE_TICKS += 1
    if _IDLE_TICKS < 3:
        return
    uiapp = sender
    if _apply_ribbon_i18n(uiapp):
        return
    if _IDLE_TICKS >= _IDLE_MAX:
        _unregister_idling(uiapp)


def _schedule_ribbon_i18n():
    global _IDLE_HANDLER, _IDLE_TICKS
    _IDLE_TICKS = 0
    try:
        import i18n
        i18n.init_from_config()
    except Exception:
        pass
    try:
        from pyrevit import HOST_APP
        uiapp = HOST_APP.uiapp
        if uiapp is None:
            _apply_ribbon_i18n(None)
            return
        if _IDLE_HANDLER is not None:
            try:
                uiapp.Idling -= _IDLE_HANDLER
            except Exception:
                pass
        _IDLE_HANDLER = _on_idling
        uiapp.Idling += _IDLE_HANDLER
    except Exception:
        _apply_ribbon_i18n(None)


_schedule_ribbon_i18n()
