# -*- coding: utf-8 -*-
"""
Post-load ribbon orchestration for pyRevit Reload / Update.

Aligned with ``sessionmgr._new_session``:

1. ``startup.py`` → ``ribbon_i18n.prepare_match_keys()`` (before ``update_pyrevit_ui``)
2. pyRevit builds UI → ``cleanup_pyrevit_ui``
3. One-shot ``Idling`` (waits for ribbon) → optional UI refresh → ``ribbon_i18n.init_from_config()``
"""
from __future__ import print_function

import os

_EXTENSION_NAME = u"AVRO"
_MIN_IDLING_TICKS = 2
_MAX_IDLING_TICKS = 90

_post_load_idling = None


def _log(msg):
    try:
        import config
        config._log(msg)
    except Exception:
        pass


def prepare_ribbon_for_pyrevit_update():
    """Called from ``startup.py`` before pyRevit rebuilds ribbon UI."""
    try:
        import ribbon_i18n
        if ribbon_i18n.prepare_match_keys():
            _log(u"reload: ribbon match keys prepared")
    except Exception as ex:
        _log(u"reload: prepare_match_keys failed: {}".format(ex))


def _avro_assembly_info():
    """Return (ui_extension, assembly_info) for AVRO, or (None, None)."""
    try:
        from pyrevit.extensions import extensionmgr
        from pyrevit.loader import asmmaker, sessioninfo
        from pyrevit.coreutils import assmutils
        import config
    except Exception as ex:
        _log(u"reload: pyRevit imports failed: {}".format(ex))
        return None, None

    try:
        assms = sessioninfo.get_loaded_pyrevit_assemblies()
    except Exception:
        return None, None

    avro_asm = None
    for assm_name in assms:
        name = config._u(assm_name)
        if _EXTENSION_NAME in name.upper():
            avro_asm = assm_name
            break
    if avro_asm is None:
        return None, None

    ui_ext = None
    try:
        for ext in extensionmgr.get_installed_ui_extensions():
            if config._u(getattr(ext, "name", None)).upper() == _EXTENSION_NAME:
                ui_ext = ext
                break
    except Exception as ex:
        _log(u"reload: extension lookup failed: {}".format(ex))
        return None, None
    if ui_ext is None:
        return None, None

    loaded = assmutils.find_loaded_asm(avro_asm)
    if isinstance(loaded, list):
        loaded = loaded[0] if loaded else None
    if loaded is None:
        return None, None

    loc = config._u(getattr(loaded, "Location", None))
    if not loc:
        return None, None

    info = asmmaker.ExtensionAssemblyInfo(
        os.path.basename(loc), loc, True)
    return ui_ext, info


def _refresh_avro_ui_if_needed():
    """Re-run ``update_pyrevit_ui`` when ``cleanup_pyrevit_ui`` hid Family Browser."""
    try:
        import ribbon_i18n
        if ribbon_i18n.has_family_browser_button():
            return False
    except Exception as ex:
        _log(u"reload: family browser check failed: {}".format(ex))

    ui_ext, info = _avro_assembly_info()
    if ui_ext is None or info is None:
        return False

    try:
        from pyrevit.loader import uimaker
        from pyrevit.coreutils import ribbon
        from pyrevit.userconfig import user_config
        uimaker.current_ui = ribbon.get_current_ui()
        ui_ext.configure()
        uimaker.update_pyrevit_ui(ui_ext, info, user_config.load_beta)
        _log(u"reload: AVRO UI refreshed after cleanup")
        return True
    except Exception as ex:
        _log(u"reload: UI refresh failed: {}".format(ex))
        return False


def _finish_post_load():
    """Refresh UI if needed, then apply ribbon language from config."""
    refreshed = False
    applied = False
    try:
        refreshed = _refresh_avro_ui_if_needed()
    except Exception as ex:
        _log(u"reload: refresh step failed: {}".format(ex))
    try:
        import ribbon_i18n
        applied = ribbon_i18n.init_from_config()
        if applied:
            _log(u"reload: ribbon i18n applied from config")
        elif refreshed:
            applied = ribbon_i18n.init_from_config()
            if applied:
                _log(u"reload: ribbon i18n applied after UI refresh")
            else:
                _log(u"reload: ribbon i18n apply returned false")
    except Exception as ex:
        _log(u"reload: ribbon i18n failed: {}".format(ex))


def schedule_post_load_ribbon_i18n():
    """One-shot Idling: wait for ribbon, then refresh UI / apply Revit UI language."""
    global _post_load_idling
    try:
        from pyrevit import HOST_APP
        uiapp = HOST_APP.uiapp
        if uiapp is None:
            _log(u"reload: HOST_APP.uiapp is None")
            return
    except Exception as ex:
        _log(u"reload: HOST_APP unavailable: {}".format(ex))
        return

    if _post_load_idling is not None:
        try:
            uiapp.Idling -= _post_load_idling
        except Exception:
            pass
        _post_load_idling = None

    state = {"n": 0}

    def on_idling(sender, args):
        global _post_load_idling
        state["n"] += 1
        if state["n"] < _MIN_IDLING_TICKS:
            return
        try:
            import ribbon_i18n
            ready = ribbon_i18n.ribbon_ui_ready()
        except Exception:
            ready = False
        if not ready and state["n"] < _MAX_IDLING_TICKS:
            return
        try:
            uiapp.Idling -= on_idling
        except Exception:
            pass
        _post_load_idling = None
        if not ready:
            _log(u"reload: ribbon not ready after {} idling ticks".format(
                state["n"]))
        _finish_post_load()

    _post_load_idling = on_idling
    try:
        uiapp.Idling += on_idling
    except Exception as ex:
        _post_load_idling = None
        _log(u"reload: Idling handler not registered: {}".format(ex))
