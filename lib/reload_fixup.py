# -*- coding: utf-8 -*-
"""
Re-apply AVRO ribbon UI after pyRevit Reload.

pyRevit ``cleanup_pyrevit_ui()`` hides panels/buttons that were not touched during
the reload pass. Schedule a second UI update on Idling so both panels appear
without restarting Revit.
"""
from __future__ import print_function


def _avro_tab_titles():
    import i18n
    return set(i18n.t("tab_title", lang=lng) for lng in (u"ru", u"en"))


def _rerun_avro_ui_update():
    import extensionmgr
    from pyrevit.loader import asmmaker, uimaker
    from pyrevit.userconfig import user_config

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
        except Exception:
            pass
        return


def _activate_avro_tab_tree():
    try:
        from pyrevit.coreutils import ribbon
    except Exception:
        return

    titles = _avro_tab_titles()
    try:
        ui = ribbon.get_current_ui()
        for tab in ui.get_pyrevit_tabs():
            try:
                title = tab.get_title() or u""
            except Exception:
                title = u""
            if title not in titles:
                continue
            try:
                tab.activate()
            except Exception:
                pass
            try:
                children = list(tab)
            except Exception:
                children = []
            for panel in children:
                try:
                    panel.activate()
                except Exception:
                    pass
                try:
                    for item in panel:
                        try:
                            item.activate()
                        except Exception:
                            pass
                except Exception:
                    pass
    except Exception:
        pass


def fix_avro_ribbon_after_reload():
    """Run after pyRevit session reload (post-cleanup)."""
    try:
        import i18n
        i18n.init_from_config()
    except Exception:
        pass
    _rerun_avro_ui_update()
    try:
        import ribbon_i18n
        ribbon_i18n.apply()
    except Exception:
        pass
    _activate_avro_tab_tree()


def schedule_after_reload():
    """Register a one-shot Idling handler (call from extension startup.py)."""
    try:
        from pyrevit import HOST_APP
        uiapp = HOST_APP.uiapp
        if uiapp is None:
            fix_avro_ribbon_after_reload()
            return

        state = {"ticks": 0, "handler": None}

        def on_idling(sender, args):
            state["ticks"] += 1
            if state["ticks"] < 3:
                return
            try:
                uiapp.Idling -= state["handler"]
            except Exception:
                pass
            fix_avro_ribbon_after_reload()

        state["handler"] = on_idling
        uiapp.Idling += on_idling
    except Exception:
        fix_avro_ribbon_after_reload()
