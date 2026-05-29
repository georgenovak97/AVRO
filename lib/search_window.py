# -*- coding: utf-8 -*-
"""Search window - command palette for Revit and AVRO commands."""
from __future__ import print_function

import os

import clr
clr.AddReference("System.Windows.Forms")

from pyrevit import forms
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent
from System import Action, IntPtr
from System.Windows import LogicalTreeHelper, Visibility
from System.Windows import GridLength, GridUnitType
from System.Windows.Controls import ListBoxItem, ScrollBarVisibility, ScrollViewer
from System.Windows.Input import Key, Keyboard
from System.Windows.Media import VisualTreeHelper
from System.Windows.Threading import DispatcherPriority
from System.Windows.Forms import Screen

import command_runner
import config
import recent_history
import revit_context
import search
import slash_commands
import ui_notify
import ui_theme

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_XAML_PATH = os.path.join(_LIB_DIR, "search_ui.xaml")
_EMPTY_SEARCH_VISIBLE_COUNT = 8
_TOP_COMMANDS_COUNT = 6

_window = None
_show_event = None
_show_handler = None


class _ResultItem(object):
    def __init__(self, entry=None, is_separator=False):
        self.IsSeparator = is_separator
        self._entry = entry

        if is_separator:
            self.Name = u""
            self.PathSuffix = u""
            self.Display = u""
            self.Title = u""
            return

        title = entry.get("search_title") or entry.get("title", u"")
        path = entry.get("path_label", u"")
        self.Name = title
        self.PathSuffix = (u" - " + path) if path else u""
        self.Display = entry.get("display") or (self.Name + self.PathSuffix)
        self.Title = self.Display

    @property
    def Entry(self):
        return self._entry


class _TopCommandItem(object):
    def __init__(self, entry):
        self._entry = entry or {}
        self.Title = (
            self._entry.get("search_title")
            or self._entry.get("title")
            or self._entry.get("display")
            or u""
        )

    @property
    def Entry(self):
        return self._entry


class SearchWindow(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(
            self, _XAML_PATH, handle_esc=False, set_owner=True
        )
        self.ShowInTaskbar = False
        self.Topmost = True

        self._entries = []
        self._history_entries = []
        self._result_items = []
        self._nav_items = []
        self._nav_index = -1
        self._in_list = False
        self._dark_theme = False
        self._top_items = []
        self.Focusable = True

        if hasattr(self, "SearchBox") and self.SearchBox is not None:
            self.SearchBox.TextChanged += self._on_search_changed
        if hasattr(self, "ClearSearchButton") and self.ClearSearchButton is not None:
            self.ClearSearchButton.Click += self._on_clear_search
        if hasattr(self, "ResultsList") and self.ResultsList is not None:
            self.ResultsList.MouseLeftButtonUp += self._on_results_click
            self.ResultsList.PreviewMouseRightButtonDown += self._on_results_right_click
        self._top_entries = []
        self._bind_top_command_slots()

        self.PreviewKeyDown += self._on_preview_key
        self.Deactivated += self._on_deactivated
        ui_notify.register_theme_listener(self._on_external_theme_changed)
        self._apply_ui_theme()
        self._refresh_all()

    def prepare_for_show(self, request_focus=True):
        import shortcuts_catalog

        try:
            self.Topmost = True
        except Exception:
            pass
        self._apply_ui_theme()
        shortcuts_catalog.refresh_available_cache()
        recent_history.clear_runtime_cache()
        slash_commands.clear_runtime_cache()
        self._in_list = False
        self._nav_index = -1
        self._refresh_all()
        self._update_clear_button()
        self._update_top_commands_visibility()
        self._clear_list_selection()
        if request_focus:
            self._defer_search_focus()

    def _apply_ui_theme(self):
        try:
            dark = config.load().get("ui_theme", "light") == "dark"
        except Exception:
            dark = False
        palette = ui_theme.DARK if dark else ui_theme.LIGHT
        self._dark_theme = dark
        try:
            ui_theme.apply_window_theme(self, palette)
        except Exception:
            pass

    def _on_external_theme_changed(self):
        try:
            if not self.IsVisible:
                return
        except Exception:
            return
        self._apply_ui_theme()

    def _defer_search_focus(self):
        def _focus():
            try:
                self.Activate()
                self.Focus()
                sb = self.SearchBox if hasattr(self, "SearchBox") else None
                if sb is not None:
                    sb.Focus()
                    Keyboard.Focus(sb)
                    sb.SelectAll()
            except Exception:
                pass

        try:
            self.Dispatcher.BeginInvoke(
                DispatcherPriority.Input, Action(_focus)
            )
        except Exception:
            pass

    def _on_deactivated(self, sender, args):
        def _maybe_hide():
            if not self.IsVisible:
                return
            if self.IsActive or self.IsKeyboardFocusWithin:
                return
            self.Hide()

        try:
            self.Dispatcher.BeginInvoke(
                DispatcherPriority.Background, Action(_maybe_hide)
            )
        except Exception:
            pass

    def _hide_to_revit(self):
        try:
            self.Topmost = False
        except Exception:
            pass
        try:
            owner = getattr(self, "Owner", None)
            if owner is not None:
                owner.Activate()
        except Exception:
            pass
        try:
            command_runner._activate_revit_main_window()
        except Exception:
            pass
        try:
            self.Hide()
        except Exception:
            pass

    def _query(self):
        if hasattr(self, "SearchBox") and self.SearchBox is not None:
            return self.SearchBox.Text or u""
        return u""

    def _update_clear_button(self):
        btn = self.ClearSearchButton if hasattr(self, "ClearSearchButton") else None
        if btn is None:
            return
        btn.Visibility = (
            Visibility.Visible
            if self._query()
            else Visibility.Collapsed
        )

    def _bind_top_command_slots(self):
        for i in range(_TOP_COMMANDS_COUNT):
            btn = getattr(self, "TopCmd{}".format(i), None)
            if btn is None:
                continue
            try:
                btn.Click += self._on_top_slot_click
            except Exception:
                pass

    def _top_slot_button(self, idx):
        return getattr(self, "TopCmd{}".format(idx), None)

    def _top_slot_text(self, idx):
        return getattr(self, "TopCmd{}Text".format(idx), None)

    def _set_top_slot_visible_count(self, count):
        bar = getattr(self, "TopCommandsBar", None)
        if bar is None:
            return
        try:
            n = max(0, min(_TOP_COMMANDS_COUNT, int(count)))
        except Exception:
            n = 0
        for i in range(_TOP_COMMANDS_COUNT):
            is_on = i < n
            try:
                col = bar.ColumnDefinitions[i]
                col.Width = (
                    GridLength(1, GridUnitType.Star)
                    if is_on
                    else GridLength(0, GridUnitType.Pixel)
                )
            except Exception:
                pass
            btn = self._top_slot_button(i)
            if btn is not None:
                try:
                    btn.Visibility = Visibility.Visible if is_on else Visibility.Collapsed
                except Exception:
                    pass

    def _build_top_commands(self, limit):
        limit_n = max(0, int(limit))
        try:
            entries = recent_history.get_most_used_entries(limit=limit_n) or []
        except Exception:
            entries = []
        return [_TopCommandItem(e) for e in entries]

    def _refresh_top_commands(self):
        items = self._build_top_commands(_TOP_COMMANDS_COUNT)
        self._top_entries = [it.Entry for it in items if it and it.Entry]
        self._set_top_slot_visible_count(_TOP_COMMANDS_COUNT)
        for i in range(_TOP_COMMANDS_COUNT):
            txt = self._top_slot_text(i)
            if txt is None:
                continue
            btn = self._top_slot_button(i)
            if i < len(self._top_entries):
                entry = self._top_entries[i]
                title = (
                    entry.get("search_title")
                    or entry.get("title")
                    or entry.get("display")
                    or u""
                )
                try:
                    txt.Text = title
                except Exception:
                    pass
                if btn is not None:
                    try:
                        btn.IsEnabled = True
                        btn.Opacity = 1.0
                    except Exception:
                        pass
            else:
                try:
                    txt.Text = u""
                except Exception:
                    pass
                if btn is not None:
                    try:
                        btn.IsEnabled = False
                        btn.Opacity = 0.35
                    except Exception:
                        pass

    def _update_top_commands_visibility(self):
        bar = self.TopCommandsBar if hasattr(self, "TopCommandsBar") else None
        if bar is None:
            return
        show = (not self._query().strip()) and bool(self._top_entries)
        bar.Visibility = Visibility.Visible if show else Visibility.Collapsed

    def _load_history(self):
        self._history_entries = recent_history.get_history_entries()

    def _separator_index(self, entries):
        has_recent = False
        for index, entry in enumerate(entries):
            if entry.get("_bucket") == "recent":
                has_recent = True
            if entry.get("_bucket") == "full":
                return index if has_recent else -1
        return -1

    def _find_scrollviewer(self, dep):
        if dep is None:
            return None
        if isinstance(dep, ScrollViewer):
            return dep
        try:
            count = VisualTreeHelper.GetChildrenCount(dep)
        except Exception:
            return None
        for i in range(count):
            try:
                child = VisualTreeHelper.GetChild(dep, i)
            except Exception:
                continue
            found = self._find_scrollviewer(child)
            if found is not None:
                return found
        return None

    def _sync_results_scrollbar(self):
        lst = self.ResultsList if hasattr(self, "ResultsList") else None
        if lst is None:
            return
        try:
            lst.UpdateLayout()
        except Exception:
            pass
        sv = self._find_scrollviewer(lst)
        if sv is None:
            return
        try:
            if sv.ScrollableHeight > 0.5:
                sv.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
            else:
                sv.VerticalScrollBarVisibility = ScrollBarVisibility.Disabled
        except Exception:
            pass

    def _defer_sync_results_scrollbar(self):
        def _apply():
            self._sync_results_scrollbar()

        try:
            self.Dispatcher.BeginInvoke(
                DispatcherPriority.Loaded, Action(_apply)
            )
        except Exception:
            _apply()

    def _refresh_results(self):
        query = self._query()
        if query.strip():
            self._entries = search.search(query)
        else:
            self._entries = list(self._history_entries[:_EMPTY_SEARCH_VISIBLE_COUNT])
        separator_index = self._separator_index(self._entries) if query.strip() else -1
        items = []
        for index, entry in enumerate(self._entries):
            if index == separator_index:
                items.append(_ResultItem(is_separator=True))
            items.append(_ResultItem(entry=entry))
        self._result_items = items
        if hasattr(self, "ResultsList") and self.ResultsList is not None:
            self.ResultsList.ItemsSource = self._result_items
        self._defer_sync_results_scrollbar()

    def _rebuild_nav_items(self):
        self._nav_items = list(self._result_items)

    def _refresh_all(self):
        self._refresh_top_commands()
        self._load_history()
        self._refresh_results()
        self._rebuild_nav_items()
        self._update_top_commands_visibility()

    def _clear_list_selection(self):
        if hasattr(self, "ResultsList") and self.ResultsList is not None:
            self.ResultsList.SelectedIndex = -1

    def _apply_nav_index(self, index):
        self._nav_index = index
        lst = self.ResultsList if hasattr(self, "ResultsList") else None
        if index < 0:
            self._clear_list_selection()
            return
        if lst is not None and index < lst.Items.Count:
            lst.SelectedIndex = index
            try:
                lst.ScrollIntoView(lst.SelectedItem)
            except Exception:
                pass

    def _results_count(self):
        return len(self._nav_items)

    def _is_selectable_index(self, index):
        return (
            0 <= index < len(self._nav_items)
            and not self._nav_items[index].IsSeparator
        )

    def _first_selectable_index(self):
        for index, item in enumerate(self._nav_items):
            if not item.IsSeparator:
                return index
        return -1

    def _next_selectable_index(self, index):
        for i in range(index + 1, len(self._nav_items)):
            if self._is_selectable_index(i):
                return i
        return -1

    def _prev_selectable_index(self, index):
        for i in range(index - 1, -1, -1):
            if self._is_selectable_index(i):
                return i
        return -1

    def _on_preview_key(self, sender, args):
        key = args.Key
        res_n = self._results_count()
        total = res_n

        if key == Key.Escape:
            self._hide_to_revit()
            args.Handled = True
            return

        if key == Key.Enter:
            self._run_selected()
            args.Handled = True
            return

        if key == Key.Down:
            if not self._in_list:
                if res_n > 0:
                    self._in_list = True
                    first_i = self._first_selectable_index()
                    if first_i >= 0:
                        self._apply_nav_index(first_i)
            elif total > 0:
                next_i = self._next_selectable_index(self._nav_index)
                if next_i >= 0:
                    self._apply_nav_index(next_i)
            self._ensure_search_focus()
            args.Handled = True
            return

        if key == Key.Up:
            if self._in_list:
                prev_i = self._prev_selectable_index(self._nav_index)
                if prev_i >= 0:
                    self._apply_nav_index(prev_i)
                else:
                    self._in_list = False
                    self._nav_index = -1
                    self._clear_list_selection()
            self._ensure_search_focus()
            args.Handled = True
            return

    def _ensure_search_focus(self):
        sb = self.SearchBox if hasattr(self, "SearchBox") else None
        if sb is None:
            return
        try:
            sb.Focus()
            Keyboard.Focus(sb)
        except Exception:
            pass

    def _on_search_changed(self, sender, args):
        self._in_list = False
        self._nav_index = -1
        self._update_clear_button()
        self._update_top_commands_visibility()
        self._refresh_results()
        self._rebuild_nav_items()
        self._clear_list_selection()

    def _on_clear_search(self, sender, args):
        sb = self.SearchBox if hasattr(self, "SearchBox") else None
        if sb is None:
            return
        sb.Text = u""
        self._update_top_commands_visibility()
        try:
            sb.Focus()
            Keyboard.Focus(sb)
        except Exception:
            pass

    def _result_index_from_source(self, source):
        lst = self.ResultsList if hasattr(self, "ResultsList") else None
        if lst is None or source is None:
            return -1
        try:
            container = ItemsControl.ContainerFromElement(lst, source)
            if isinstance(container, ListBoxItem):
                return lst.ItemContainerGenerator.IndexFromContainer(container)
        except Exception:
            pass
        current = source
        while current is not None:
            if isinstance(current, ListBoxItem):
                try:
                    return lst.ItemContainerGenerator.IndexFromContainer(current)
                except Exception:
                    return -1
            try:
                parent = VisualTreeHelper.GetParent(current)
                if parent is not None:
                    current = parent
                    continue
            except Exception:
                pass
            try:
                parent = LogicalTreeHelper.GetParent(current)
                if parent is not None:
                    current = parent
                    continue
            except Exception:
                pass
            try:
                current = getattr(current, "Parent", None)
            except Exception:
                current = None
        return -1

    def _on_results_click(self, sender, args):
        self._in_list = True
        lst = self.ResultsList
        if lst is not None and lst.SelectedIndex >= 0:
            self._nav_index = lst.SelectedIndex
        if not self._is_selectable_index(self._nav_index):
            return
        self._run_selected()

    def _on_results_right_click(self, sender, args):
        index = self._result_index_from_source(args.OriginalSource)
        if not self._is_selectable_index(index):
            return
        item = self._nav_items[index]
        entry = item.Entry
        if not entry:
            return

        query = self._query().strip()
        if (not query) or entry.get("_bucket") != "recent":
            return

        recent_history.remove_search_recent(entry.get("key"))
        self._in_list = False
        self._nav_index = -1
        self._refresh_all()
        self._clear_list_selection()
        self._ensure_search_focus()
        args.Handled = True

    def _on_top_slot_click(self, sender, args):
        if sender is None:
            return
        idx = -1
        try:
            name = getattr(sender, "Name", "") or ""
            if name.startswith("TopCmd"):
                idx = int(name.replace("TopCmd", ""))
        except Exception:
            idx = -1
        if idx < 0 or idx >= len(self._top_entries):
            return
        entry = self._top_entries[idx]
        if not entry:
            return
        action = entry.get("action")
        if action == "family_browser":
            self._hide_to_revit()
            if command_runner.run_family_browser():
                recent_history.record(entry.get("key"))
                return
            try:
                self.Topmost = True
            except Exception:
                pass
            try:
                self.Show()
                self._defer_search_focus()
            except Exception:
                pass
            return
        self._hide_to_revit()
        if command_runner.post_command_sync(entry.get("command_id")):
            recent_history.record(entry.get("key"))
            return
        try:
            self.Topmost = True
        except Exception:
            pass
        try:
            self.Show()
            self._defer_search_focus()
        except Exception:
            pass

    def _run_selected(self):
        entry = None
        if self._in_list and 0 <= self._nav_index < len(self._nav_items):
            item = self._nav_items[self._nav_index]
            if item.IsSeparator:
                return
            entry = item.Entry
        if entry is None and self._nav_items:
            first_i = self._first_selectable_index()
            if first_i >= 0:
                entry = self._nav_items[first_i].Entry
        if not entry:
            return
        action = entry.get("action")
        if action == "family_browser":
            self._hide_to_revit()
            if command_runner.run_family_browser():
                recent_history.record(entry.get("key"))
                return
            try:
                self.Topmost = True
            except Exception:
                pass
            try:
                self.Show()
                self._defer_search_focus()
            except Exception:
                pass
            return
        if action == "clear_all_history":
            recent_history.clear_all_history()
            self.Hide()
            try:
                self.Dispatcher.BeginInvoke(
                    DispatcherPriority.Background, Action(_show_on_ui_thread)
                )
            except Exception:
                _show_on_ui_thread()
            return
        self._hide_to_revit()
        if command_runner.post_command_sync(entry.get("command_id")):
            recent_history.record(entry.get("key"))
            return
        try:
            self.Topmost = True
        except Exception:
            pass
        try:
            self.Show()
            self._defer_search_focus()
        except Exception:
            pass


def _center_search_on_screen(win):
    from System.Windows import Point, PresentationSource

    left_px = 0.0
    top_px = 0.0
    sw_px = 0.0
    sh_px = 0.0
    try:
        hwnd = command_runner.get_revit_main_window_handle()
        screen = Screen.FromHandle(IntPtr(hwnd)) if hwnd else Screen.PrimaryScreen
        if screen is not None:
            area = screen.WorkingArea
            left_px = float(area.Left)
            top_px = float(area.Top)
            sw_px = float(area.Width)
            sh_px = float(area.Height)
    except Exception:
        pass

    win.UpdateLayout()
    left = left_px
    top = top_px
    sw = sw_px
    sh = sh_px
    try:
        source = PresentationSource.FromVisual(win)
        target = source.CompositionTarget if source is not None else None
        if target is not None:
            transform = target.TransformFromDevice
            tl = transform.Transform(Point(left_px, top_px))
            br = transform.Transform(Point(left_px + sw_px, top_px + sh_px))
            left = tl.X
            top = tl.Y
            sw = br.X - tl.X
            sh = br.Y - tl.Y
    except Exception:
        pass

    sb = win.SearchBox if hasattr(win, "SearchBox") else None
    try:
        if sb is not None:
            w = sb.ActualWidth if sb.ActualWidth > 0 else max(100.0, win.Width - 20.0)
            h = sb.ActualHeight if sb.ActualHeight > 0 else 30.0
            center_in_window = sb.TranslatePoint(Point(w / 2.0, h / 2.0), win)
        else:
            ww = win.ActualWidth if win.ActualWidth > 0 else win.Width
            wh = win.ActualHeight if win.ActualHeight > 0 else win.Height
            center_in_window = Point(ww / 2.0, wh / 2.0)
    except Exception:
        ww = win.ActualWidth if win.ActualWidth > 0 else win.Width
        wh = win.ActualHeight if win.ActualHeight > 0 else win.Height
        center_in_window = Point(ww / 2.0, wh / 2.0)

    win.Left = left + (sw / 2.0) - center_in_window.X
    win.Top = top + (sh / 2.0) - center_in_window.Y


class _ShowSearchHandler(IExternalEventHandler):
    def Execute(self, uiapp):
        _show_on_ui_thread()

    def GetName(self):
        return "Search Show"


def _show_on_ui_thread():
    if not revit_context.is_project_document_active():
        return
    global _window
    if _window is None:
        _window = SearchWindow()
    if hasattr(_window, "SearchBox") and _window.SearchBox is not None:
        _window.SearchBox.Text = u""
    _window.prepare_for_show(request_focus=False)
    _window.Show()
    _window.UpdateLayout()
    _center_search_on_screen(_window)
    _window._defer_search_focus()


def prepare_external_event():
    global _show_event, _show_handler
    if _show_event is not None:
        return True
    try:
        _show_handler = _ShowSearchHandler()
        _show_event = ExternalEvent.Create(_show_handler)
        return _show_event is not None
    except Exception:
        return False


def request_show():
    if _show_event is None:
        return
    try:
        _show_event.Raise()
    except Exception:
        pass


def show():
    if not revit_context.is_project_document_active():
        return
    prepare_external_event()
    _show_on_ui_thread()


def is_visible():
    global _window
    if _window is None:
        return False
    try:
        return bool(_window.IsVisible)
    except Exception:
        return False
