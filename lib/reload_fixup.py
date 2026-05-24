# -*- coding: utf-8 -*-
"""
Post-load ribbon orchestration for pyRevit Reload / Update.

Works with pyRevit ``sessionmgr._new_session`` order:

1. ``startup.py`` → ``ribbon_i18n.prepare_match_keys()`` (before ``update_pyrevit_ui``)
2. pyRevit builds UI → ``cleanup_pyrevit_ui``
3. One-shot ``Idling`` → optional UI refresh → ``ribbon_i18n.init_from_config()``
"""
from __future__ import print_function

_EXTENSION_NAME = u"AVRO"
_IDLING_TICKS_BEFORE_FINISH = 2

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
        import extensionmgr
        from pyrevit.loader import asmmaker, sessioninfo
        from pyrevit.coreutils import assmutils, coreutils
    except Exception:
        return None, None

    try:
        assms = sessioninfo.get_loaded_pyrevit_assemblies()
    except Exception:
        return None, None

    avro_asm = None
    for assm_name in assms:
        name = assm_name if isinstance(assm_name, unicode) else unicode(assm_name)
        if _EXTENSION_NAME in name.upper():
            avro_asm = assm_name
            break
    if avro_asm is None:
        return None, None

    ui_ext = None
    for ext in extensionmgr.get_installed_ui_extensions():
        if (getattr(ext, "name", None) or u"").upper() == _EXTENSION_NAME:
            ui_ext = ext
            break
    if ui_ext is None:
        return None, None

    loaded = assmutils.find_loaded_asm(avro_asm)
    if isinstance(loaded, list):
        loaded = loaded[0] if loaded else None
    if loaded is None:
        return None, None

    loc = getattr(loaded, "Location", None) or u""
    if isinstance(loc, str):
        try:
            loc = unicode(loc)
        except Exception:
            loc = u""
    if not loc:
        return None, None

    info = asmmaker.ExtensionAssemblyInfo(
        coreutils.get_file_name(loc), loc, True)
    return ui_ext, info


def _refresh_avro_ui_if_needed():
    """Re-run ``update_pyrevit_ui`` when ``cleanup_pyrevit_ui`` hid Family Browser."""
    try:
        import ribbon_i18n
        if ribbon_i18n.has_family_browser_button():
            return False
    except Exception:
        pass

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


def schedule_post_load_ribbon_i18n():
    """One-shot Idling handler: refresh UI if needed, then apply ``ui_language``."""
    global _post_load_idling
    try:
        from pyrevit import HOST_APP
        uiapp = HOST_APP.uiapp
        if uiapp is None:
            return
    except Exception:
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
        if state["n"] < _IDLING_TICKS_BEFORE_FINISH:
            return
        try:
            uiapp.Idling -= on_idling
        except Exception:
            pass
        _post_load_idling = None
        try:
            _refresh_avro_ui_if_needed()
            import ribbon_i18n
            if ribbon_i18n.init_from_config():
                _log(u"reload: ribbon i18n applied from config")
        except Exception as ex:
            _log(u"reload: post-load ribbon failed: {}".format(ex))

    _post_load_idling = on_idling
    try:
        uiapp.Idling += on_idling
    except Exception as ex:
        _post_load_idling = None
        _log(u"reload: Idling handler not registered: {}".format(ex))
