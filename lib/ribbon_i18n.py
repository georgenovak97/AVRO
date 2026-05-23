# -*- coding: utf-8 -*-
"""Apply AVRO ribbon labels from config ui_language."""
from __future__ import print_function

_BRAILLE_PANEL = u"\u2800"


def _texts_for_key(key):
    import i18n
    return set(
        i18n.t(key, lang=lng)
        for lng in (u"ru", u"en")
    )


def _set_item_label(item, text):
    if item is None or not text:
        return
    try:
        if hasattr(item, "Text"):
            item.Text = text
    except Exception:
        pass
    try:
        src = getattr(item, "Source", None)
        if src is not None and hasattr(src, "Title"):
            src.Title = text
    except Exception:
        pass
    try:
        from Autodesk.Revit.UI import PushButton
        rvt = getattr(item, "GetRevitItem", None)
        if rvt is not None:
            pb = rvt()
            if isinstance(pb, PushButton):
                pb.ItemText = text
    except Exception:
        pass


def _walk_items(container):
    if container is None:
        return
    items = getattr(container, "Items", None)
    if items is None:
        src = getattr(container, "Source", None)
        items = getattr(src, "Items", None) if src is not None else None
    if items is None:
        return
    try:
        count = items.Count
    except Exception:
        count = len(items)
    for i in range(count):
        try:
            it = items[i]
        except Exception:
            continue
        if it is None:
            continue
        sub = getattr(it, "Items", None)
        if sub is not None:
            try:
                if sub.Count > 0:
                    _walk_items(it)
                    continue
            except Exception:
                pass
        yield it


def apply(lang=None):
    """Update tab, panel, and button captions on the AVRO ribbon tab."""
    try:
        import clr
        clr.AddReference("AdWindows")
        from Autodesk.Windows import ComponentManager
    except Exception:
        return False

    try:
        import config
        import i18n
    except Exception:
        return False

    lng = lang or config.get_ui_language()
    i18n.set_language(lng)

    tab_names = _texts_for_key("tab_title")
    tools_names = _texts_for_key("ribbon_panel_tools")
    settings_names = _texts_for_key("settings_dialog_title")
    fm_names = _texts_for_key("ribbon_title") | {
        u"\u0411\u0440\u0430\u0443\u0437\u0435\u0440 \u0441\u0435\u043c\u0435\u0439\u0441\u0442\u0432",
        u"Family Manager",
    }

    new_tab = i18n.t("tab_title")
    new_tools = i18n.t("ribbon_panel_tools")
    new_settings = i18n.t("settings_dialog_title")
    new_fm = i18n.t("ribbon_title")

    updated = False
    try:
        for tab in ComponentManager.Ribbon.Tabs:
            if tab is None:
                continue
            try:
                if not tab.IsVisible:
                    continue
            except Exception:
                pass
            title = tab.Title or u""
            if title not in tab_names:
                continue
            tab.Title = new_tab
            updated = True
            for panel in tab.Panels:
                src = getattr(panel, "Source", None)
                if src is None:
                    continue
                ptitle = src.Title or u""
                if ptitle in tools_names:
                    src.Title = new_tools
                for item in _walk_items(panel):
                    label = u""
                    try:
                        label = item.Text or u""
                    except Exception:
                        pass
                    if not label:
                        try:
                            label = item.Source.Title or u""
                        except Exception:
                            label = u""
                    if label in settings_names:
                        _set_item_label(item, new_settings)
                    elif label in fm_names:
                        _set_item_label(item, new_fm)
            break
    except Exception:
        return False
    return updated


def init_from_config():
    try:
        import config
        return apply(config.get_ui_language())
    except Exception:
        return False
