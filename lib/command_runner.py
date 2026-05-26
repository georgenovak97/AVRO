# -*- coding: utf-8 -*-
"""Run Revit commands by ``CommandId`` from Search UI."""
from __future__ import print_function

import ctypes

import clr

clr.AddReference("RevitAPIUI")

from Autodesk.Revit.UI import RevitCommandId
from pyrevit import HOST_APP

_user32 = ctypes.windll.user32


def _u(text):
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    try:
        return unicode(text)
    except Exception:
        return unicode(str(text), "utf-8", "ignore")


def _activate_revit_main_window():
    try:
        uiapp = HOST_APP.uiapp if HOST_APP is not None else None
        if uiapp is None:
            return
        hwnd = getattr(uiapp, "MainWindowHandle", 0)
        if not hwnd:
            return
        _user32.ShowWindow(hwnd, 5)
        _user32.BringWindowToTop(hwnd)
        _user32.SetForegroundWindow(hwnd)
        _user32.SetActiveWindow(hwnd)
    except Exception:
        pass


def post_command_sync(command_id):
    """Run a command synchronously from the Search UI thread."""
    cid = _u(command_id)
    if not cid:
        return False
    try:
        rcid = RevitCommandId.LookupCommandId(cid)
        if rcid is None:
            return False
        _activate_revit_main_window()
        HOST_APP.uiapp.PostCommand(rcid)
        return True
    except Exception:
        return False


def is_command_available(command_id):
    cid = _u(command_id)
    if not cid:
        return False
    try:
        rcid = RevitCommandId.LookupCommandId(cid)
        return rcid is not None
    except Exception:
        return False
