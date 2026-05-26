# -*- coding: utf-8 -*-
"""Double-tap left Ctrl to open Search."""
from __future__ import print_function

import ctypes
from ctypes import wintypes
import os
import threading
import time

try:
    import __builtin__ as _builtins
except ImportError:
    import builtins as _builtins

import config

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
HC_ACTION = 0

VK_LCTRL = 0xA2

_TAP_WINDOW_SEC = 0.55
_TAP_DEBOUNCE_SEC = 0.04
_TRIGGER_COOLDOWN = 0.45

_on_activate = None
_is_blocked = None
_installed = False
_last_trigger = 0.0
_tap_times = []
_lctrl_was_down = False
_idling_handler = None
_hook_proc_ref = None
_hook_id = None
_hook_thread = None

_TMP_DIR = config.SEARCH_STATE_DIR


def _shared_runtime():
    runtime = getattr(_builtins, "_avro_search_hotkey_runtime", None)
    if runtime is None:
        runtime = {
            "hook_thread": None,
            "idling_handler": None,
            "uiapp": None,
        }
        setattr(_builtins, "_avro_search_hotkey_runtime", runtime)
    return runtime


def _ensure_tmp_dir():
    try:
        if not os.path.isdir(_TMP_DIR):
            os.makedirs(_TMP_DIR)
    except Exception:
        pass


def _log_path():
    _ensure_tmp_dir()
    return os.path.join(_TMP_DIR, "search_hotkey.log")


def _log(msg):
    try:
        line = u"[{}] {}\n".format(
            time.strftime("%H:%M:%S"),
            msg if isinstance(msg, unicode) else unicode(msg),
        )
        with open(_log_path(), "a") as f:
            f.write(line.encode("utf-8", "replace"))
    except Exception:
        pass


def _search_open():
    if not _is_blocked:
        return False
    try:
        return bool(_is_blocked())
    except Exception:
        return False


def _is_revit_foreground():
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) == int(_kernel32.GetCurrentProcessId())
    except Exception:
        return False


def _is_left_ctrl_key(vk, scan):
    try:
        if int(vk) == VK_LCTRL:
            return True
    except Exception:
        pass
    return False


def _trigger():
    global _last_trigger
    if not _is_revit_foreground():
        _tap_times[:] = []
        return
    if _search_open():
        return
    now = time.time()
    if now - _last_trigger < _TRIGGER_COOLDOWN:
        return
    _last_trigger = now
    if not _on_activate:
        return
    try:
        _on_activate()
        _log(u"trigger left ctrl left ctrl")
    except Exception as ex:
        _log(u"activate: {}".format(ex))


def _register_left_ctrl_tap():
    global _tap_times
    if not _is_revit_foreground():
        _tap_times = []
        return
    if _search_open():
        _tap_times = []
        return
    now = time.time()
    if _tap_times and (now - _tap_times[-1]) < _TAP_DEBOUNCE_SEC:
        return
    _tap_times = [t for t in _tap_times if (now - t) <= _TAP_WINDOW_SEC]
    _tap_times.append(now)
    if len(_tap_times) >= 2:
        _tap_times = []
        _trigger()


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]


def _low_level_proc(nCode, wParam, lParam):
    try:
        if nCode == HC_ACTION and wParam == WM_KEYDOWN:
            kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if _is_left_ctrl_key(kb.vkCode, kb.scanCode):
                _register_left_ctrl_tap()
    except Exception as ex:
        _log(u"hook: {}".format(ex))
    return _user32.CallNextHookEx(_hook_id, nCode, wParam, lParam)


def _hook_thread_main():
    global _hook_proc_ref, _hook_id
    try:
        _hook_proc_ref = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )(_low_level_proc)
        _hook_id = _user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, _hook_proc_ref, None, 0
        )
        if not _hook_id:
            _log(u"hook fail err={}".format(_kernel32.GetLastError()))
            return
        _log(u"hook left ctrl OK")
        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
    except Exception as ex:
        _log(u"hook thread: {}".format(ex))
    finally:
        if _hook_id:
            _user32.UnhookWindowsHookEx(_hook_id)
            _hook_id = None


def _start_hook_thread():
    global _hook_thread
    runtime = _shared_runtime()
    shared_thread = runtime.get("hook_thread")
    if shared_thread is not None and shared_thread.is_alive():
        _hook_thread = shared_thread
        return
    _hook_thread = threading.Thread(target=_hook_thread_main)
    _hook_thread.daemon = True
    _hook_thread.start()
    runtime["hook_thread"] = _hook_thread


def _left_ctrl_key_down():
    try:
        return (_user32.GetAsyncKeyState(VK_LCTRL) & 0x8000) != 0
    except Exception:
        return False


def _poll_keyboard():
    global _lctrl_was_down, _tap_times
    if (not _is_revit_foreground()) or _search_open():
        _lctrl_was_down = False
        _tap_times = []
        return
    down = _left_ctrl_key_down()
    if down and not _lctrl_was_down:
        _register_left_ctrl_tap()
    _lctrl_was_down = down


def _on_idling(sender, args):
    _poll_keyboard()


def _register_idling():
    global _idling_handler
    _unregister_idling()
    try:
        from pyrevit import HOST_APP

        uiapp = HOST_APP.uiapp
        if uiapp is None:
            return False
        runtime = _shared_runtime()
        existing_handler = runtime.get("idling_handler")
        if existing_handler is not None and runtime.get("uiapp") is uiapp:
            _idling_handler = existing_handler
            return True
        _idling_handler = _on_idling
        uiapp.Idling += _idling_handler
        runtime["idling_handler"] = _idling_handler
        runtime["uiapp"] = uiapp
        _log(u"idling OK")
        return True
    except Exception as ex:
        _log(u"idling: {}".format(ex))
        return False


def _unregister_idling():
    global _idling_handler
    if _idling_handler is None:
        return
    try:
        from pyrevit import HOST_APP

        HOST_APP.uiapp.Idling -= _idling_handler
    except Exception:
        pass
    _idling_handler = None


def _prepare_search_event():
    try:
        import search_window

        search_window.prepare_external_event()
    except Exception as ex:
        _log(u"prepare: {}".format(ex))


def install(activate_callback, is_blocked=None):
    global _on_activate, _is_blocked, _tap_times, _lctrl_was_down
    global _installed

    _on_activate = activate_callback
    _is_blocked = is_blocked
    _tap_times = []
    _lctrl_was_down = False
    _start_hook_thread()
    _register_idling()
    _installed = True
    _prepare_search_event()
    _log(u"install left ctrl left ctrl")


def ensure_installed(activate_callback, is_blocked=None):
    if (
        _installed
        and _on_activate is activate_callback
        and _is_blocked is is_blocked
    ):
        return
    install(activate_callback, is_blocked=is_blocked)
