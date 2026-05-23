# -*- coding: utf-8 -*-
"""Apply AVRO ribbon labels and pyRevit-style tooltips from config ui_language."""
from __future__ import print_function

_BRAILLE_PANEL = u"\u2800"
_RIBBON_AUTHOR = u"AVRO Consulting"

# Revit internal command names (see pyRevit Bundle Name footer).
_BUNDLE_SETTINGS = u"Settings"
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


def _is_text(value):
    try:
        basestring
        return isinstance(value, basestring)
    except NameError:
        return isinstance(value, (str, unicode))


def _texts_for_key(key):
    import i18n
    return set(
        i18n.t(key, lang=lng)
        for lng in (u"ru", u"en")
    )


def _pyrevit_tooltip_body(description, bundle_name, author=_RIBBON_AUTHOR):
    """Same layout as pyRevit ``_make_button_tooltip`` (description + bundle + author)."""
    body = _as_unicode(description).strip()
    if body:
        body += u"\n\n"
    body += u"Bundle Name:\n{} (pushbutton)".format(
        bundle_name or u"AVRO")
    if author:
        body += u"\n\nAuthor(s):\n{}".format(author)
    return body


def _get_revit_pushbutton(item):
    try:
        from Autodesk.Revit.UI import PushButton
        rvt = getattr(item, "GetRevitItem", None)
        if rvt is None:
            return None
        pb = rvt()
        if isinstance(pb, PushButton):
            return pb
    except Exception:
        pass
    return None


def _tip_matches(tip, variants):
    if not tip:
        return False
    if tip in variants:
        return True
    for variant in variants:
        if variant and variant in tip:
            return True
    return False


def _read_tooltip_text(item, pb=None):
    if pb is None:
        pb = _get_revit_pushbutton(item)
    if pb is not None:
        try:
            tip = pb.ToolTip
            if _is_text(tip) and tip:
                return _as_unicode(tip)
        except Exception:
            pass
    if item is None:
        return u""
    try:
        tip = item.ToolTip
    except Exception:
        return u""
    if tip is None:
        return u""
    if _is_text(tip):
        return _as_unicode(tip)
    try:
        content = getattr(tip, "Content", None)
        if content:
            return _as_unicode(content)
    except Exception:
        pass
    return u""


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
    pb = _get_revit_pushbutton(item)
    if pb is not None:
        try:
            pb.ItemText = text
        except Exception:
            pass


def _set_item_pyrevit_tooltip(item, title, description, bundle_name):
    """Full Revit/pyRevit tooltip: title, description, Bundle Name, Author(s)."""
    if item is None:
        return
    title = _as_unicode(title).strip()
    pb = _get_revit_pushbutton(item)
    name = bundle_name
    if not name and pb is not None:
        try:
            name = _as_unicode(pb.Name)
        except Exception:
            name = u""
    if not name:
        name = title.replace(u" ", u"") or u"AVRO"
    full_tip = _pyrevit_tooltip_body(description, name)

    if pb is not None:
        try:
            pb.ToolTip = full_tip
        except Exception:
            pass
        try:
            pb.LongDescription = u""
        except Exception:
            pass

    try:
        import clr
        clr.AddReference("AdWindows")
        from Autodesk.Windows import RibbonToolTip
        rt = RibbonToolTip()
        rt.Title = title
        rt.Content = full_tip
        item.ToolTip = rt
        resolve = getattr(item, "ResolveToolTip", None)
        if resolve is not None:
            resolve()
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
    """Update tab, panel, button captions, and pyRevit-style tooltips."""
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
    settings_tips = _texts_for_key("settings_ribbon_tooltip")
    fm_names = _texts_for_key("ribbon_title") | {
        u"\u0411\u0440\u0430\u0443\u0437\u0435\u0440 \u0441\u0435\u043c\u0435\u0439\u0441\u0442\u0432",
        u"Family Manager",
    }
    fm_tips = _texts_for_key("ribbon_tooltip")

    new_tab = i18n.t("tab_title")
    new_tools = i18n.t("ribbon_panel_tools")
    new_settings = i18n.t("settings_dialog_title")
    new_settings_tip = i18n.t("settings_ribbon_tooltip")
    new_fm = i18n.t("ribbon_title")
    new_fm_tip = i18n.t("ribbon_tooltip")

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
                    pb = _get_revit_pushbutton(item)
                    tip = _read_tooltip_text(item, pb)
                    if (label in settings_names
                            or _tip_matches(tip, settings_tips)):
                        _set_item_label(item, new_settings)
                        _set_item_pyrevit_tooltip(
                            item, new_settings, new_settings_tip,
                            _BUNDLE_SETTINGS)
                    elif (label in fm_names
                            or _tip_matches(tip, fm_tips)):
                        _set_item_label(item, new_fm)
                        _set_item_pyrevit_tooltip(
                            item, new_fm, new_fm_tip,
                            _BUNDLE_FAMILY_BROWSER)
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
