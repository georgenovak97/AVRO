# -*- coding: utf-8 -*-
"""Bridge current AVRO extension to integrated Search runtime."""
from __future__ import print_function

_bootstrap = None


def _log(msg):
    try:
        import config
        config._log(msg)
    except Exception:
        pass


def search_runtime_exists():
    try:
        import search_window
        import hotkey
        return search_window is not None and hotkey is not None
    except Exception:
        return False


def _activate():
    import search_window
    search_window.request_show()


def _blocked():
    import search_window
    return search_window.is_visible()


def _install_search():
    import search_window
    import hotkey
    hotkey.ensure_installed(_activate, is_blocked=_blocked)
    search_window.prepare_external_event()


def _on_bootstrap(sender, args):
    global _bootstrap
    try:
        from pyrevit import HOST_APP
        if _bootstrap is not None and HOST_APP is not None and HOST_APP.uiapp is not None:
            HOST_APP.uiapp.Idling -= _bootstrap
    except Exception:
        pass
    _bootstrap = None
    try:
        _install_search()
        _log(u"search: bootstrap installed")
    except Exception as ex:
        _log(u"search: bootstrap failed: {}".format(ex))


def _schedule_bootstrap():
    global _bootstrap
    try:
        from pyrevit import HOST_APP
        uiapp = HOST_APP.uiapp
        if uiapp is None:
            return False
        if _bootstrap is not None:
            try:
                uiapp.Idling -= _bootstrap
            except Exception:
                pass
        _bootstrap = _on_bootstrap
        uiapp.Idling += _bootstrap
        return True
    except Exception as ex:
        _log(u"search: bootstrap schedule failed: {}".format(ex))
        return False


def ensure_search_started():
    """Install Search hotkey + external event from AVRO startup."""
    if not search_runtime_exists():
        _log(u"search: runtime modules are missing")
        return False
    try:
        from pyrevit import HOST_APP
        if HOST_APP is not None and HOST_APP.uiapp is not None:
            _install_search()
            _log(u"search: runtime installed")
            return True
    except Exception as ex:
        _log(u"search: direct install failed: {}".format(ex))
    return _schedule_bootstrap()


def show_search():
    """Open Search window from AVRO pushbutton."""
    if not ensure_search_started():
        _log(u"search: runtime unavailable for pushbutton")
        try:
            from pyrevit import forms
            forms.alert(
                u"Search runtime is unavailable.",
                title=u"AVRO",
                warn_icon=True,
            )
        except Exception:
            pass
        return False
    import search_window
    search_window.show()
    return True
