# -*- coding: utf-8 -*-
"""AVRO settings: theme, GitHub, LinkedIn."""
import os
import sys
import codecs

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System")

from System.Windows import MessageBox, MessageBoxButton, Thickness
from System.Windows.Markup import XamlReader
from System.Windows.Media import SolidColorBrush, ColorConverter
from System.Diagnostics import Process

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_EXT_LIB = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "..", "lib"))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)

import config
import i18n
import ribbon_i18n
import ui_notify
import ui_theme

_URL_GITHUB = "https://github.com/georgenovak97/AVRO"
_URL_LINKEDIN = "https://www.linkedin.com/in/georgenovak97/"

def _load_dialog_xaml():
    path = os.path.join(_THIS_DIR, "settings_dialog.xaml")
    with codecs.open(path, "r", "utf-8") as f:
        return XamlReader.Parse(f.read())


def _find_named(root, name):
    if root is None:
        return None
    ctrl = root.FindName(name)
    if ctrl is not None:
        return ctrl
    from System.Windows.Media import VisualTreeHelper
    from System.Windows import FrameworkElement
    count = VisualTreeHelper.GetChildrenCount(root)
    for i in range(count):
        child = VisualTreeHelper.GetChild(root, i)
        if isinstance(child, FrameworkElement) and child.Name == name:
            return child
        found = _find_named(child, name)
        if found is not None:
            return found
    return None


def _brush(hex_color):
    return SolidColorBrush(ColorConverter.ConvertFromString(hex_color))


def _mark_option(btn, selected, dark):
    if btn is None:
        return
    palette = ui_theme.DARK if dark else ui_theme.LIGHT
    if selected:
        btn.Background = _brush(palette["SelBg"])
        btn.BorderBrush = _brush(palette["SelBorder"])
    else:
        btn.Background = _brush(palette["BtnFace"])
        btn.BorderBrush = _brush(palette["BtnBorder"])
    btn.BorderThickness = Thickness(1)


def _apply_dialog_text(controls):
    mapping = (
        ("btn_theme_light", "settings_theme_light"),
        ("btn_theme_dark", "settings_theme_dark"),
        ("btn_gh", "settings_github"),
        ("btn_li", "settings_linkedin"),
        ("btn_ok", "btn_ok"),
    )
    for key, i18n_key in mapping:
        btn = controls.get(key)
        if btn is not None:
            btn.Content = i18n.t(i18n_key)


def _refresh_selection(controls, theme):
    dark = theme == "dark"
    _mark_option(controls.get("btn_theme_light"), theme == "light", dark)
    _mark_option(controls.get("btn_theme_dark"), theme == "dark", dark)


def _show_settings_dialog():
    cfg = config.load()
    cur_lang = config.read_ui_language()
    i18n.set_language(cur_lang)
    ribbon_i18n.apply(cur_lang)
    cur_theme = (cfg.get("ui_theme") or "light").lower()

    win = _load_dialog_xaml()
    win.Title = i18n.t("settings_dialog_title")
    ui_theme.apply_window_theme(
        win, ui_theme.DARK if cur_theme == "dark" else ui_theme.LIGHT)

    controls = {
        "btn_theme_light": _find_named(win, "BtnThemeLight"),
        "btn_theme_dark": _find_named(win, "BtnThemeDark"),
        "btn_ok": _find_named(win, "BtnOk"),
        "btn_gh": _find_named(win, "BtnGithub"),
        "btn_li": _find_named(win, "BtnLinkedIn"),
    }
    if controls["btn_theme_light"] is None or controls["btn_ok"] is None:
        MessageBox.Show(
            u"Settings dialog controls not found.",
            i18n.t("settings_dialog_title"),
            MessageBoxButton.OK)
        return

    selection = {"theme": cur_theme}

    def _apply_text_and_selection():
        _apply_dialog_text(controls)
        _refresh_selection(controls, selection["theme"])

    _apply_text_and_selection()

    def on_theme_light(sender, e):
        selection["theme"] = "light"
        ui_theme.apply_window_theme(win, ui_theme.LIGHT)
        _refresh_selection(controls, selection["theme"])

    def on_theme_dark(sender, e):
        selection["theme"] = "dark"
        ui_theme.apply_window_theme(win, ui_theme.DARK)
        _refresh_selection(controls, selection["theme"])

    def on_ok(sender, e):
        new_theme = selection["theme"]
        if new_theme != cur_theme:
            config.set_value("ui_theme", new_theme)
            ui_notify.notify_theme_changed()
        win.Close()

    def on_github(sender, e):
        Process.Start(_URL_GITHUB)

    def on_linkedin(sender, e):
        Process.Start(_URL_LINKEDIN)

    controls["btn_theme_light"].Click += on_theme_light
    controls["btn_theme_dark"].Click += on_theme_dark
    controls["btn_ok"].Click += on_ok
    if controls["btn_gh"] is not None:
        controls["btn_gh"].Click += on_github
    if controls["btn_li"] is not None:
        controls["btn_li"].Click += on_linkedin

    win.ShowDialog()


_show_settings_dialog()
