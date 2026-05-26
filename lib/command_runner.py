# -*- coding: utf-8 -*-
"""Run Revit commands by ``CommandId`` from Search UI."""
from __future__ import print_function

import ctypes
import codecs
import os

import clr

clr.AddReference("RevitAPIUI")

from Autodesk.Revit.UI import RevitCommandId, IExternalEventHandler, ExternalEvent
from pyrevit import HOST_APP

_user32 = ctypes.windll.user32
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FAMILY_BROWSER_SCRIPT = os.path.join(
    _ROOT_DIR,
    "AVRO.tab",
    "02_Tools.panel",
    "FamilyBrowser.pushbutton",
    "script.py",
)
_family_browser_event = None
_family_browser_handler = None


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


def _run_family_browser_sync():
    if not os.path.isfile(_FAMILY_BROWSER_SCRIPT):
        return False
    scope = {
        "__file__": _FAMILY_BROWSER_SCRIPT,
        "__name__": "__main__",
    }
    try:
        with codecs.open(_FAMILY_BROWSER_SCRIPT, "r", "utf-8") as stream:
            code = compile(stream.read(), _FAMILY_BROWSER_SCRIPT, "exec")
        exec code in scope, scope
        return True
    except Exception:
        return False


class _RunFamilyBrowserHandler(IExternalEventHandler):
    def Execute(self, uiapp):
        _run_family_browser_sync()

    def GetName(self):
        return "Family Browser Run"


def prepare_family_browser_event():
    global _family_browser_event, _family_browser_handler
    if _family_browser_event is not None:
        return True
    try:
        _family_browser_handler = _RunFamilyBrowserHandler()
        _family_browser_event = ExternalEvent.Create(_family_browser_handler)
        return _family_browser_event is not None
    except Exception:
        return False


def run_family_browser():
    """Open Family Browser from Search slash command in API context."""
    try:
        _activate_revit_main_window()
    except Exception:
        pass
    if not prepare_family_browser_event():
        return False
    try:
        _family_browser_event.Raise()
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
