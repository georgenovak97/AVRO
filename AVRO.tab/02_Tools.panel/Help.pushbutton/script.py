# -*- coding: utf-8 -*-
"""AVRO Help: browse and read a local Obsidian Markdown vault."""
import os
import sys
import System

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Windows.Forms")

from System.Windows import Thickness, VerticalAlignment, Visibility
from System.Windows.Controls import TreeViewItem, TextBlock, StackPanel, Orientation, ListBoxItem
from System.Windows.Media import Color, Geometry, SolidColorBrush, Stretch
from System.Windows.Shapes import Path as WpfPath
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
        self.search_mode = False
        self.doc_count = 0
        self._history = []
        self._history_index = -1
        self._history_navigating = False

    def _palette(self):
        return ui_theme.DARK if config.load().get("ui_theme") == "dark" else ui_theme.LIGHT

    def _apply_text(self):
        self.win.Title = i18n.t("help_app_title")
        self.ui.TocTitle.Text = i18n.t("help_toc_title")
        self.ui.BtnDocuments.Content = i18n.t("help_btn_documents")
        self.ui.BtnDocuments.ToolTip = i18n.t("help_btn_documents_tooltip")
        self.ui.BtnRefresh.Content = i18n.t("help_btn_refresh")
        self.ui.BtnRefresh.ToolTip = i18n.t("help_btn_refresh_tooltip")
        self.ui.SearchBox.ToolTip = i18n.t("help_search_placeholder")

    def _header(self, text, geometry):
        panel = StackPanel()
        panel.Orientation = Orientation.Horizontal
        icon = WpfPath()
        icon.Data = Geometry.Parse(geometry)
        icon.Width = 16
        icon.Height = 16
        icon.Stretch = Stretch.Uniform
        icon.Margin = Thickness(3, 1, 5, 1)
        palette = self._palette()
        color = palette["TreeIcon"].lstrip("#")
        icon.Stroke = SolidColorBrush(Color.FromRgb(
            int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)))
        icon.StrokeThickness = 1.2
        panel.Children.Add(icon)
        label = TextBlock(Text=text)
        label.VerticalAlignment = VerticalAlignment.Center
        panel.Children.Add(label)
        return panel

    def _theme_changed(self):
        if self.win is not None:
            palette = self._palette()
            ui_theme.apply_window_theme(self.win, palette)
            if self.current_path and os.path.isfile(self.current_path):
                self._show_file(self.current_path)

    def _add_file(self, parent, path):
        item = TreeViewItem()
        item.Header = self._header(
            os.path.splitext(os.path.basename(path))[0],
            "M3,1 L12,1 L16,5 L16,17 L3,17 Z M12,1 L12,5 L16,5 M5,9 L14,9 M5,12 L14,12 M5,15 L11,15")
        item.Tag = path
        item.Uid = "file"
        item.Selected += self._file_selected
        parent.Items.Add(item)

    def _add_search_item(self):
        item = TreeViewItem()
        item.Header = self._header(i18n.t("help_search"), "M2,2 L16,2 L16,16 L2,16 Z M5,6 L13,6 M5,9 L13,9 M5,12 L10,12")
        item.Tag = "__search__"
        item.Selected += self._search_selected
        item.PreviewMouseLeftButtonDown += self._search_mouse_down
        self.ui.DocumentTree.Items.Add(item)

    def _search_mouse_down(self, sender, args):
        if sender.IsSelected:
            self._search_selected(sender, args)

    def _add_folder(self, parent, node, is_root=False):
        item = TreeViewItem()
        item.Header = self._header(
            node.name, "M1,4 L6,4 L8,6 L17,6 L17,16 L1,16 Z")
        item.Tag = node.path
        item.IsExpanded = is_root
        for folder in node.folders:
            self._add_folder(item, folder, is_root=False)
        for path in node.files:
            self._add_file(item, path)
        parent.Items.Add(item)

    def _load_tree(self):
        self.ui.DocumentTree.Items.Clear()
        self._add_search_item()
        path = config.load().get("docs_path") or ""
        if not os.path.isdir(path):
            return
        self.root, count = help_scanner.scan_documents(path)
        self.doc_count = count
        self._add_folder(self.ui.DocumentTree, self.root, is_root=True)

    def _file_selected(self, sender, args):
        path = getattr(sender, "Tag", None)
        if path and os.path.isfile(path):
            self._show_file(path)

    def _search_selected(self, sender, args):
        self.search_mode = True
        self.ui.SearchBar.Visibility = Visibility.Visible
        self.ui.PathText.Text = u"{} {}".format(
            self.doc_count, i18n.t("help_documents_label"))
        self.ui.SearchBox.Text = ""
        self.ui.SearchBox.Focus()
        self._run_search("")

    def _update_navigation_buttons(self):
        if self.ui is None:
            return
        self.ui.BtnBack.IsEnabled = self._history_index > 0
        self.ui.BtnForward.IsEnabled = (
            self._history_index >= 0
            and self._history_index < len(self._history) - 1)

    def _go_back(self, sender=None, args=None):
        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._history_navigating = True
        try:
            target = self._history[self._history_index]
            if target == "__search__":
                self._search_selected(None, None)
            else:
                self._show_file(target)
        finally:
            self._history_navigating = False
            self._update_navigation_buttons()

    def _go_forward(self, sender=None, args=None):
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        self._history_navigating = True
        try:
            target = self._history[self._history_index]
            if target == "__search__":
                self._search_selected(None, None)
            else:
                self._show_file(target)
        finally:
            self._history_navigating = False
            self._update_navigation_buttons()

    def _run_search(self, query):
        path = config.load().get("docs_path") or ""
        query = (query or "").strip()
        if not query:
            recent = [path for path in config.load_recent_documents()
                      if os.path.isfile(path)]
            self.ui.MarkdownBrowser.NavigateToString(
                help_renderer.recent_results_html(recent, self._palette()))
            return
        results = help_scanner.search_documents(path, query)
        self.ui.MarkdownBrowser.NavigateToString(help_renderer.search_results_html(
            results, query, self._palette(), i18n.t("help_search"),
            i18n.t("help_search_no_results"), i18n.t("help_search_results")))

    def _clear_search(self):
        self.ui.SearchBox.Text = ""
        self.ui.SearchBox.Focus()

    def _on_browser_navigating(self, sender, args):
        uri = args.Uri
        if uri is None or uri.Scheme != "help" or uri.Host != "open":
            return
        query = uri.Query
        if query.startswith("?path="):
            path = System.Uri.UnescapeDataString(query[6:]).replace("/", os.sep)
            if os.path.isfile(path):
                self._show_file(path)
        args.Cancel = True

    def _show_file(self, path):
        try:
            text = help_scanner.read_text(path)
            if not self._history_navigating:
                self._history = self._history[:self._history_index + 1]
                if self.search_mode and (
                        not self._history or self._history[-1] != "__search__"):
                    self._history.append("__search__")
                if not self._history or self._history[-1].lower() != path.lower():
                    self._history.append(path)
                self._history_index = len(self._history) - 1
            self.current_path = path
            self._current_text = text
            self.search_mode = False
            self.ui.SearchBar.Visibility = Visibility.Collapsed
            config.add_recent_document(path)
            self.ui.PathText.Text = path
            self.ui.MarkdownBrowser.NavigateToString(
                help_renderer.themed_html(
                    text, self._palette(), os.path.basename(path), os.path.dirname(path)))
            self._headings = help_toc.extract_headings(text)
            self._fill_toc()
            self._update_navigation_buttons()
        except Exception as ex:
            self.ui.PathText.Text = u"{}: {}".format(i18n.t("help_select_file"), ex)

    def _fill_toc(self):
        self.ui.TocTree.Items.Clear()
        if not self._headings:
            empty = TextBlock(Text=i18n.t("help_toc_empty"))
            self.ui.TocTree.Items.Add(empty)
            return
        for level, title in self._headings:
            text = TextBlock(Text=title)
            text.Margin = Thickness((level - 1) * 12, 0, 0, 0)
            item = ListBoxItem(Content=text, Tag=title)
            item.Selected += self._toc_selected
            self.ui.TocTree.Items.Add(item)

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
            self.win, ("DocumentTree", "MarkdownBrowser", "PathText", "BtnBack",
                       "BtnForward", "SearchBar", "SearchBox",
                       "BtnClearSearch", "TocTitle", "TocTree", "BtnDocuments",
                       "BtnRefresh"))
        ui_theme.apply_window_theme(self.win, self._palette())
        self._apply_text()
        self.ui.BtnDocuments.Click += self._choose_documents
        self.ui.BtnRefresh.Click += lambda sender, args: self._load_tree()
        self.ui.BtnBack.Click += self._go_back
        self.ui.BtnForward.Click += self._go_forward
        self.ui.MarkdownBrowser.Navigating += self._on_browser_navigating
        self.ui.SearchBox.TextChanged += lambda sender, args: self.search_mode and self._run_search(sender.Text)
        self.ui.BtnClearSearch.Click += lambda sender, args: self._clear_search()
        ui_notify.register_theme_listener(self._theme_changed)
        self._load_tree()
        self._search_selected(None, None)

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
