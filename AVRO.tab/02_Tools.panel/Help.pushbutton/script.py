# -*- coding: utf-8 -*-
"""AVRO Help: browse and read a local Obsidian Markdown vault."""
import os
import sys

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Windows.Forms")

from System.Windows import Thickness
from System.Windows.Controls import TreeViewItem, TextBlock
from System.Windows.Forms import FolderBrowserDialog, DialogResult

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_EXT_LIB = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "..", "lib"))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)

import config
import help_renderer
import help_scanner
import help_toc
import i18n
import ui_notify
import ui_theme
import ui_utils


class HelpDialog(object):
    def __init__(self):
        self.win = None
        self.ui = None
        self.root = None
        self.current_path = None
        self._current_text = ""
        self._headings = []

    def _palette(self):
        return ui_theme.DARK if config.load().get("ui_theme") == "dark" else ui_theme.LIGHT

    def _apply_text(self):
        self.win.Title = i18n.t("help_app_title")
        self.ui.TocTitle.Text = i18n.t("help_toc_title")
        self.ui.BtnDocuments.Content = i18n.t("help_btn_documents")
        self.ui.BtnDocuments.ToolTip = i18n.t("help_btn_documents_tooltip")
        self.ui.BtnRefresh.Content = i18n.t("help_btn_refresh")
        self.ui.BtnRefresh.ToolTip = i18n.t("help_btn_refresh_tooltip")

    def _theme_changed(self):
        if self.win is not None:
            palette = self._palette()
            ui_theme.apply_window_theme(self.win, palette)
            if self.current_path and os.path.isfile(self.current_path):
                self._show_file(self.current_path)

    def _add_file(self, parent, path):
        item = TreeViewItem()
        item.Header = TextBlock(Text=os.path.splitext(os.path.basename(path))[0])
        item.Tag = path
        item.Selected += self._file_selected
        parent.Items.Add(item)

    def _add_folder(self, parent, node):
        item = TreeViewItem()
        item.Header = TextBlock(Text=node.name)
        item.Tag = node.path
        item.IsExpanded = True
        for folder in node.folders:
            self._add_folder(item, folder)
        for path in node.files:
            self._add_file(item, path)
        parent.Items.Add(item)

    def _load_tree(self):
        self.ui.DocumentTree.Items.Clear()
        path = config.load().get("docs_path") or ""
        if not os.path.isdir(path):
            self.ui.StatusText.Text = i18n.t("help_no_documents")
            return
        self.ui.StatusText.Text = i18n.t("help_status_loading")
        self.root, count = help_scanner.scan_documents(path)
        self._add_folder(self.ui.DocumentTree, self.root)
        self.ui.StatusText.Text = i18n.t("help_status_files", n=count)

    def _file_selected(self, sender, args):
        path = getattr(sender, "Tag", None)
        if path and os.path.isfile(path):
            self._show_file(path)

    def _show_file(self, path):
        try:
            text = help_scanner.read_text(path)
            self.current_path = path
            self._current_text = text
            self.ui.PathText.Text = path
            self.ui.MarkdownBrowser.NavigateToString(
                help_renderer.themed_html(
                    text, self._palette(), os.path.basename(path), os.path.dirname(path)))
            self._headings = help_toc.extract_headings(text)
            self._fill_toc()
            self.ui.StatusText.Text = os.path.basename(path)
        except Exception as ex:
            self.ui.StatusText.Text = u"{}: {}".format(i18n.t("help_select_file"), ex)

    def _fill_toc(self):
        self.ui.TocTree.Items.Clear()
        if not self._headings:
            empty = TreeViewItem()
            empty.Header = i18n.t("help_toc_empty")
            self.ui.TocTree.Items.Add(empty)
            return
        stack = [(0, self.ui.TocTree)]
        for level, title in self._headings:
            while stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1]
            item = TreeViewItem(Header=TextBlock(Text=title), Tag=title)
            item.Margin = Thickness((level - 1) * 8, 0, 0, 0)
            item.Selected += self._toc_selected
            parent.Items.Add(item)
            stack.append((level, item))

    def _toc_selected(self, sender, args):
        title = getattr(sender, "Tag", None)
        if title and self.current_path:
            self.ui.MarkdownBrowser.NavigateToString(
                help_renderer.themed_html(
                    self._current_text, self._palette(),
                    os.path.basename(self.current_path),
                    os.path.dirname(self.current_path),
                    help_renderer._slug(title)))

    def _choose_documents(self, sender, args):
        dialog = FolderBrowserDialog()
        dialog.Description = i18n.t("help_btn_documents_tooltip")
        current = config.load().get("docs_path") or ""
        if os.path.isdir(current):
            dialog.SelectedPath = current
        if dialog.ShowDialog() == DialogResult.OK:
            config.set_value("docs_path", dialog.SelectedPath)
            self._load_tree()

    def _init_window(self):
        self.win = ui_utils.load_xaml(_THIS_DIR)
        self.ui = ui_utils.NamedUiControls(
            self.win, ("DocumentTree", "MarkdownBrowser", "PathText", "TocTitle",
                       "TocTree", "StatusText", "BtnDocuments", "BtnRefresh"))
        ui_theme.apply_window_theme(self.win, self._palette())
        self._apply_text()
        self.ui.BtnDocuments.Click += self._choose_documents
        self.ui.BtnRefresh.Click += lambda sender, args: self._load_tree()
        ui_notify.register_theme_listener(self._theme_changed)
        self._load_tree()
        if not self.current_path:
            self.ui.PathText.Text = i18n.t("help_select_file")

    def show(self):
        i18n.init_from_config()
        self._init_window()
        try:
            self.win.ShowDialog()
        finally:
            ui_notify.unregister_theme_listener(self._theme_changed)
            self.win = None
            self.ui = None


HelpDialog().show()
