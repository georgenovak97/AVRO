# -*- coding: utf-8 -*-
"""
Ribbon stability across pyRevit Reload (local Reload, not remote Update).

Never calls ``asmmaker.create_assembly`` after Reload — that can race with
pyRevit session load and break Reload telemetry (``result_dict`` is None).
"""
from __future__ import print_function

_PYREVIT_TAB_KEY = u"AVRO"
_PYREVIT_TOOLS_PANEL_KEY = u"Tools"
_BRAILLE_PANEL = u"\u2800"
_BUNDLE_FAMILY_BROWSER = u"FamilyBrowser"


def _as_unicode(text):
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    try:
        return unicode(text)
    except Exception:
        return u""


def _tools_panel_title_variants():
    import i18n
    names = set(i18n.t("ribbon_panel_tools", lang=lng) for lng in (u"ru", u"en"))
    names.add(_PYREVIT_TOOLS_PANEL_KEY)
    return names


def _session_ready():
    """True when Reload finished and AVRO assembly is registered."""
    try:
        from pyrevit.loader import sessioninfo
        assms = sessioninfo.get_loaded_pyrevit_assemblies()
        return any(u"AVRO" in _as_unicode(a).upper() for a in assms)
    except Exception:
        return False


def prepare_ribbon_for_pyrevit_update():
    """Reset AVRO tab/panel keys before pyRevit ``update_pyrevit_ui`` (startup)."""
    try:
        import ribbon_i18n
        tab = ribbon_i18n.find_avro_tab()
    except Exception:
        tab = None
    if tab is None:
        return

    variants = _tools_panel_title_variants()
    try:
        tab.Title = _PYREVIT_TAB_KEY
    except Exception:
        pass
    try:
        for panel in tab.Panels:
            src = getattr(panel, "Source", None)
            if src is None:
                continue
            ptitle = _as_unicode(getattr(src, "Title", None) or u"")
            if ptitle == _BRAILLE_PANEL:
                continue
            if ptitle in variants:
                try:
                    src.Title = _PYREVIT_TOOLS_PANEL_KEY
                except Exception:
                    pass
    except Exception:
        pass

    try:
        from pyrevit import HOST_APP
        for rpanel in HOST_APP.uiapp.GetRibbonPanels(_PYREVIT_TAB_KEY):
            pname = _as_unicode(rpanel.Name)
            if pname in variants:
                try:
                    rpanel.Visible = True
                except Exception:
                    pass
    except Exception:
        pass


def _get_avro_asm_info(ui_ext):
    """Reuse DLL from current session (no new assembly build)."""
    try:
        import os
        from pyrevit.loader import asmmaker
        from pyrevit.loader import sessioninfo
        from pyrevit.coreutils import assmutils, appdata, coreutils
        from pyrevit import framework
    except Exception:
        return None

    ext_key = _as_unicode(getattr(ui_ext, "name", None) or u"AVRO").upper()
    try:
        for assm_name in sessioninfo.get_loaded_pyrevit_assemblies():
            if ext_key not in _as_unicode(assm_name).upper():
                continue
            loaded = assmutils.find_loaded_asm(assm_name)
            if not loaded:
                continue
            if isinstance(loaded, list):
                if not loaded:
                    continue
                loaded = loaded[0]
            loc = _as_unicode(getattr(loaded, "Location", None) or u"")
            if loc:
                fname = coreutils.get_file_name(loc)
                return asmmaker.ExtensionAssemblyInfo(fname, loc, True)
    except Exception:
        pass

    try:
        for path in appdata.list_data_files(framework.ASSEMBLY_FILE_TYPE):
            base = os.path.basename(path).upper()
            if ext_key in base:
                fname = coreutils.get_file_name(path)
                return asmmaker.ExtensionAssemblyInfo(fname, path, True)
    except Exception:
        pass
    return None


def _rerun_avro_ui_update():
    """Second UI pass using the already-loaded AVRO DLL."""
    if not _session_ready():
        return False
    try:
        import extensionmgr
        from pyrevit.loader import uimaker
        from pyrevit.coreutils import ribbon
        from pyrevit.userconfig import user_config
    except Exception:
        return False

    try:
        uimaker.current_ui = ribbon.get_current_ui()
    except Exception:
        return False

    prepare_ribbon_for_pyrevit_update()

    for ui_ext in extensionmgr.get_installed_ui_extensions():
        ext_name = (getattr(ui_ext, "name", None) or u"").upper()
        if ext_name != u"AVRO":
            continue
        ext_asm_info = _get_avro_asm_info(ui_ext)
        if ext_asm_info is None:
            return False
        try:
            ui_ext.configure()
            uimaker.update_pyrevit_ui(
                ui_ext, ext_asm_info, user_config.load_beta)
            return True
        except Exception:
            return False
    return False


def _activate_pyrvt_tree(container):
    if container is None:
        return
    try:
        container.activate()
    except Exception:
        pass
    try:
        for child in container:
            _activate_pyrvt_tree(child)
    except Exception:
        pass


def _activate_avro_ribbon():
    try:
        import ribbon_i18n
        tab = ribbon_i18n.find_avro_tab()
    except Exception:
        tab = None
    if tab is not None:
        try:
            tab.IsVisible = True
            tab.IsEnabled = True
        except Exception:
            pass
        try:
            for panel in tab.Panels:
                try:
                    panel.IsVisible = True
                    panel.IsEnabled = True
                except Exception:
                    pass
                src = getattr(panel, "Source", None)
                if src is not None:
                    try:
                        src.IsVisible = True
                        src.IsEnabled = True
                    except Exception:
                        pass
        except Exception:
            pass

    try:
        import ribbon_i18n
        pyrvt_tab = ribbon_i18n._find_avro_pyrvt_tab()
        if pyrvt_tab is not None:
            _activate_pyrvt_tree(pyrvt_tab)
    except Exception:
        pass


def _family_browser_on_ribbon():
    try:
        import ribbon_i18n
        tab = ribbon_i18n.find_avro_tab()
        if tab is None:
            return False
        for panel in tab.Panels:
            try:
                items = panel.Source.Items
                count = items.Count
            except Exception:
                continue
            for i in range(count):
                try:
                    it = items[i]
                    pb = ribbon_i18n._get_revit_pushbutton(it)
                    if pb is None:
                        continue
                    if _as_unicode(pb.Name) == _BUNDLE_FAMILY_BROWSER:
                        return True
                except Exception:
                    pass
    except Exception:
        pass
    return False


def fix_after_reload():
    """Restore ribbon labels and Family Browser (safe after Reload completes)."""
    if not _session_ready():
        return
    prepare_ribbon_for_pyrevit_update()
    if not _family_browser_on_ribbon():
        _rerun_avro_ui_update()
    try:
        import ribbon_i18n
        ribbon_i18n.apply()
    except Exception:
        pass
    _activate_avro_ribbon()


def schedule_after_reload():
    """Post-Reload: wait for session, then fix ribbon (does not block Reload)."""
    try:
        from pyrevit import HOST_APP
        uiapp = HOST_APP.uiapp
        if uiapp is None:
            return

        state = {"ticks": 0, "handler": None, "min_ticks": 8, "max_ticks": 60}

        def on_idling(sender, args):
            state["ticks"] += 1
            if state["ticks"] < state["min_ticks"]:
                return
            if not _session_ready():
                if state["ticks"] >= state["max_ticks"]:
                    try:
                        uiapp.Idling -= state["handler"]
                    except Exception:
                        pass
                return
            try:
                fix_after_reload()
            except Exception:
                pass
            try:
                uiapp.Idling -= state["handler"]
            except Exception:
                pass

        state["handler"] = on_idling
        uiapp.Idling += on_idling
    except Exception:
        pass
