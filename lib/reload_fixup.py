# -*- coding: utf-8 -*-
"""
Ribbon stability across pyRevit Reload (local Reload, not remote Update).

pyRevit matches the Tools panel by a single internal name (``Tools``).
Localized panel titles in bundle.yaml break that on some Revit locales.
"""
from __future__ import print_function

_PYREVIT_TAB_KEY = u"AVRO"
_PYREVIT_TOOLS_PANEL_KEY = u"Tools"
_BRAILLE_PANEL = u"\u2800"
_BUNDLE_FAMILY_BROWSER = u"FamilyBrowser"
_BUNDLE_SETTINGS = u"Settings"


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
    """All panel titles that may exist from older sessions or locales."""
    import i18n
    names = set(i18n.t("ribbon_panel_tools", lang=lng) for lng in (u"ru", u"en"))
    names.add(_PYREVIT_TOOLS_PANEL_KEY)
    return names


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


def _rerun_avro_ui_update():
    """Second UI pass with a fresh ``current_ui`` (after cleanup)."""
    try:
        import extensionmgr
        from pyrevit.loader import asmmaker, uimaker
        from pyrevit.coreutils import ribbon
        from pyrevit.userconfig import user_config
    except Exception:
        return False

    uimaker.current_ui = ribbon.get_current_ui()
    prepare_ribbon_for_pyrevit_update()

    for ui_ext in extensionmgr.get_installed_ui_extensions():
        ext_name = (getattr(ui_ext, "name", None) or u"").upper()
        if ext_name != u"AVRO":
            continue
        try:
            ui_ext.configure()
            ext_asm_info = asmmaker.create_assembly(ui_ext)
            if ext_asm_info:
                uimaker.update_pyrevit_ui(
                    ui_ext, ext_asm_info, user_config.load_beta)
                return True
        except Exception:
            pass
        break
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
                try:
                    items = panel.Source.Items
                    for i in range(items.Count):
                        it = items[i]
                        try:
                            it.IsVisible = True
                            it.IsEnabled = True
                        except Exception:
                            pass
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
    """Restore Family Browser after local Reload + cleanup."""
    prepare_ribbon_for_pyrevit_update()
    if not _family_browser_on_ribbon():
        _rerun_avro_ui_update()
    try:
        import ribbon_i18n
        ribbon_i18n.apply()
    except Exception:
        pass
    _activate_avro_ribbon()
    if not _family_browser_on_ribbon():
        _rerun_avro_ui_update()
        try:
            import ribbon_i18n
            ribbon_i18n.apply()
        except Exception:
            pass
        _activate_avro_ribbon()


def apply_ribbon_labels():
    try:
        import ribbon_i18n
        return ribbon_i18n.apply()
    except Exception:
        return False


def schedule_after_reload():
    """Post-Reload: rebuild UI if needed, then localize labels."""
    try:
        from pyrevit import HOST_APP
        uiapp = HOST_APP.uiapp
        if uiapp is None:
            fix_after_reload()
            return

        state = {"ticks": 0, "handler": None, "max_ticks": 50}

        def on_idling(sender, args):
            state["ticks"] += 1
            if state["ticks"] < 2:
                return
            done = False
            try:
                fix_after_reload()
                done = _family_browser_on_ribbon()
            except Exception:
                pass
            if done or state["ticks"] >= state["max_ticks"]:
                try:
                    uiapp.Idling -= state["handler"]
                except Exception:
                    pass

        state["handler"] = on_idling
        uiapp.Idling += on_idling
    except Exception:
        fix_after_reload()
