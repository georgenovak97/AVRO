# -*- coding: utf-8 -*-
"""
Ribbon stability across pyRevit Reload.

pyRevit matches tabs/panels by internal keys (``AVRO``, ``Tools`` / Revit locale).
``ribbon_i18n`` only changes button labels; tab/panel *keys* are restored here
before ``update_pyrevit_ui`` (extension ``startup.py``, before UI build).
"""
from __future__ import print_function

_PYREVIT_TAB_KEY = u"AVRO"
_BRAILLE_PANEL = u"\u2800"


def _as_unicode(text):
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    try:
        return unicode(text)
    except Exception:
        return u""


def _tools_panel_titles():
    import i18n
    return set(i18n.t("ribbon_panel_tools", lang=lng) for lng in (u"ru", u"en"))


def _tools_title_for_pyrevit():
    """Panel key pyRevit will use on this Revit session (Revit locale, not AVRO config)."""
    import i18n
    try:
        from pyrevit.coreutils import applocales
        loc = applocales.get_current_applocale()
        code = _as_unicode(getattr(loc, "lang_code", None) or u"").lower()
        if code.startswith(u"ru"):
            return i18n.t("ribbon_panel_tools", lang=u"ru")
    except Exception:
        pass
    return i18n.t("ribbon_panel_tools", lang=u"en")


def prepare_ribbon_for_pyrevit_update():
    """Reset AVRO tab/panel keys before pyRevit ``update_pyrevit_ui`` (startup)."""
    try:
        import ribbon_i18n
        tab = ribbon_i18n.find_avro_tab()
    except Exception:
        tab = None
    if tab is None:
        return

    tools_expected = _tools_title_for_pyrevit()
    tools_variants = _tools_panel_titles()

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
            if ptitle in tools_variants:
                try:
                    src.Title = tools_expected
                except Exception:
                    pass
    except Exception:
        pass


def _activate_avro_panels_adwindows():
    try:
        import ribbon_i18n
        tab = ribbon_i18n.find_avro_tab()
    except Exception:
        tab = None
    if tab is None:
        return

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


def apply_ribbon_labels():
    try:
        import ribbon_i18n
        return ribbon_i18n.apply()
    except Exception:
        return False


def schedule_after_reload():
    """After Reload + cleanup, apply AVRO button/tab labels (retry on Idling)."""
    try:
        from pyrevit import HOST_APP
        uiapp = HOST_APP.uiapp
        if uiapp is None:
            apply_ribbon_labels()
            _activate_avro_panels_adwindows()
            return

        state = {"ticks": 0, "handler": None, "max_ticks": 40}

        def on_idling(sender, args):
            state["ticks"] += 1
            if apply_ribbon_labels():
                try:
                    uiapp.Idling -= state["handler"]
                except Exception:
                    pass
                _activate_avro_panels_adwindows()
                return
            if state["ticks"] >= state["max_ticks"]:
                try:
                    uiapp.Idling -= state["handler"]
                except Exception:
                    pass
                _activate_avro_panels_adwindows()

        state["handler"] = on_idling
        uiapp.Idling += on_idling
    except Exception:
        apply_ribbon_labels()
        _activate_avro_panels_adwindows()
