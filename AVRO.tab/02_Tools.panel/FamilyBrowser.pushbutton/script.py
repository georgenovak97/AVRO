# -*- coding: utf-8 -*-
"""
Family Browser — pyRevit extension (AVRO)
Entry point script.
"""
import os
import re
import sys
import threading
import time

# ---------------------------------------------------------------------------
# CLR / .NET imports
# ---------------------------------------------------------------------------
import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System.Windows.Forms")

import System
from System.Windows import (
    Thickness, HorizontalAlignment, VerticalAlignment, Visibility,
    TextWrapping, FontWeights,
)
from System.Windows.Controls import (
    TreeViewItem, TextBlock, Canvas, Border, Button,
)
from System.Windows.Controls.Primitives import ToggleButton
from System.Windows.Media import SolidColorBrush, Color, VisualTreeHelper
from System.Windows.Input import Key, MouseButton, Keyboard, ModifierKeys
from System.Windows.Threading import DispatcherTimer
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    Family as RevitFamily,
    Transaction,
)
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, script

# ---------------------------------------------------------------------------
# Extension lib path
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_EXT_LIB  = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "..", "lib"))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)

import config
import family_scanner as scanner
import family_inspector
import rfa_preview
import library_cache as libcache
import avro_log
import ui_theme
import i18n
import ribbon_i18n
import ui_notify
import family_utils
import ui_utils
import image_utils
import family_load_options
import family_browser_props
import family_browser_cards
import card_layout
import family_browser_status
import family_browser_library
from revit_utils import as_unicode, revit_name

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------


def _brush(r, g, b):
    c = Color.FromRgb(r, g, b)
    br = SolidColorBrush(c)
    br.Freeze()
    return br


COL_CARD            = None
COL_CARD_HOV        = None
COL_CARD_SEL        = None
COL_CARD_SEL_BORDER = None
COL_TEXT            = None
COL_MUTED           = None
COL_BORDER          = None


def _sync_card_colors(palette):
    global COL_CARD, COL_CARD_HOV, COL_CARD_SEL, COL_CARD_SEL_BORDER
    global COL_TEXT, COL_MUTED, COL_BORDER
    brushes = ui_theme.card_brushes(palette)
    COL_CARD = brushes["card"]
    COL_CARD_HOV = brushes["hover"]
    COL_CARD_SEL = brushes["sel"]
    COL_CARD_SEL_BORDER = brushes["sel_border"]
    COL_BORDER = brushes["border"]
    COL_TEXT = brushes["text"]
    COL_MUTED = brushes["muted"]


_sync_card_colors(ui_theme.LIGHT)

_UI_CONTROL_NAMES = [
    "SearchBox", "SearchHint", "LblFolder", "BtnClearSearch",
    "PropsTitle", "PropsHint", "PropsPanel",
    "CategoryTree", "BtnSettings", "BtnReload", "BtnLoad",
    "FamilyPanel", "FamilyScrollViewer",
    "BreadcrumbText", "CountText", "StatusText",
]


# ---------------------------------------------------------------------------
# Load XAML
# ---------------------------------------------------------------------------
_TAG_FOLDER_PREFIX = u"folder:"
# Build medium folder grids in UI batches so the window stays responsive.
_CARD_UI_BATCH = 50
_CARD_UI_BATCH_THRESHOLD = 50
_CARD_UI_BUDGET_S = 0.020
_PREVIEW_MEM_LIMIT = 512
_PREVIEW_FLUSH_BATCH = 5
_PREVIEW_STATUS_INTERVAL_S = 0.15
# Above this count only visible cards are created (virtual scroll).
_VIRTUAL_THRESHOLD = 250
_VIRTUAL_ROW_BUFFER = 2
_VIRTUAL_ITEM_LIMIT = 50
_SEARCH_DEBOUNCE_MS = 400
_GRID_RELOAD_DEBOUNCE_MS = 80
_DOUBLE_ESC_CLOSE_WINDOW_S = 0.6
_CARD_OUTER_PAD = 8
_CARD_W = 156
_CARD_H = 182
_CARD_MIN_W = 132
_CARD_MAX_W = 220
_PREVIEW_W = 96
_PREVIEW_H = 67
_STICKY_KEY = "AVRO_session"


def _library_cache_key(paths):
    return libcache.cache_key(paths)


def _load_sticky_session():
    try:
        if hasattr(script, "get_sticky"):
            data = script.get_sticky(_STICKY_KEY, None)
        else:
            data = getattr(script, "sticky", {}).get(_STICKY_KEY)
        if not data:
            return None, {}, set()
        sk = data.get("key")
        if sk is not None and not isinstance(sk, tuple):
            sk = tuple(sk)
        misses = data.get("preview_miss", {})
        if not isinstance(misses, dict):
            misses = {}
        return sk, {}, misses
    except Exception:
        return None, {}, {}


def _save_sticky_session(key, preview_mem, preview_miss):
    try:
        payload = None
        if key is not None:
            payload = {
                "key": list(key),
                # BitmapImage instances are WPF objects and are not sticky-safe.
                "preview_mem": {},
                "preview_miss": dict(preview_miss or {}),
            }
        if hasattr(script, "set_sticky"):
            script.set_sticky(_STICKY_KEY, payload)
        elif hasattr(script, "sticky"):
            if payload is None:
                script.sticky.pop(_STICKY_KEY, None)
            else:
                script.sticky[_STICKY_KEY] = payload
    except Exception:
        pass

def _make_card(fi, dialog, card_w=None, card_h=None):
    """Build a WPF card for one family (grid with preview)."""
    return family_browser_cards.make_card(
        fi, dialog, dialog._card_brushes,
        card_w or _CARD_W, card_h or _CARD_H, _PREVIEW_W, _PREVIEW_H)

def _apply_card_metrics(card, preview_img, card_w, card_h):
    """Size card + preview image to current adaptive cell."""
    family_browser_cards.apply_card_metrics(
        card, preview_img, card_w, card_h, _PREVIEW_W, _PREVIEW_H)

# ---------------------------------------------------------------------------
# Dialog class
# ---------------------------------------------------------------------------
class FamilyBrowserDialog(object):

    def _file_signature(self, path):
        try:
            stat = os.stat(path)
            return {"mtime": float(stat.st_mtime), "size": int(stat.st_size)}
        except (IOError, OSError):
            return None

    def _valid_preview_misses(self, entries):
        result = {}
        for path, expected in (entries or {}).items():
            signature = self._file_signature(path)
            if signature is None or not isinstance(expected, dict):
                continue
            try:
                if (float(expected.get("mtime")) == signature["mtime"]
                        and int(expected.get("size")) == signature["size"]):
                    result[path] = signature
            except (TypeError, ValueError):
                continue
        return result

    def _restore_preview_misses(self, key=None):
        key = key or self._cache_key()
        disk_entries = libcache.load_preview_misses(key)
        sticky_key, _sticky_mem, sticky_entries = _load_sticky_session()
        sticky_norm = libcache.cache_key(list(sticky_key)) if sticky_key else None
        restored = dict(disk_entries)
        if sticky_norm == key:
            restored.update(sticky_entries)
        validated = self._valid_preview_misses(restored)
        with self._preview_mem_lock:
            self._preview_miss = validated

    def _release_number(self, value):
        """Return a two-digit Revit release number from R23 or 2023 text."""
        text = as_unicode(value or u"")
        match = re.search(r"20(\d{2})", text)
        if match:
            return int(match.group(1))
        match = re.search(r"\bR?(\d{2})\b", text, re.I)
        if match:
            return int(match.group(1))
        return None

    def _current_revit_label(self):
        """Return the running Revit release label, for example ``R22``."""
        try:
            app = self.doc.Application
            number = self._release_number(
                getattr(app, "VersionNumber", u""))
            if number is None:
                number = self._release_number(
                    getattr(app, "VersionName", u""))
            if number is not None:
                return u"R{:02d}".format(number)
        except Exception:
            pass
        return u""

    def __init__(self):
        self.win = None
        self.ui = None
        self.doc = revit.doc
        self.cfg = config.load()
        i18n.set_language(config.read_ui_language())
        self._scan = {"roots": [], "all": [], "index": {}}
        self._active = []
        self._preview_gen = 0
        self._preview_mem = {}
        self._preview_mem_lock = threading.RLock()
        self._preview_order = []
        self._preview_miss = {}
        self._card_views = {}
        self._preview_worker_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._preview_worker_running = False
        self._preview_worker_thread = None
        self._preview_pending_request = None
        self._card_by_path = {}
        self._fi_by_path = {}
        self._all_fi_by_path = {}
        self._order_paths = []
        self._path_to_index = {}
        self._selected_paths = set()
        self._anchor_path = None
        self._load_mode = False
        self._hover_card = None
        self._family_panel_bound = None
        self._folder_scope = []
        self._folder_scope_label = u""
        self._scope_is_recent = False
        self._active_search_query = u""
        self._search_suppress = False
        self._search_timer = None
        self._grid_relayout_gen = 0
        self._grid_relayout_timer = None
        # Extract preview from .rfa when thumb cache is empty (visible items only in virtual mode).
        self._browse_disk_only = False
        self._card_build_gen = 0
        self._initial_load_started = False
        self._load_state = "idle"
        self._initial_load_result = None
        self._pending_scan_result = None
        self._pending_symbol_id = None
        self._pending_family_name = u""
        self._pending_family_path = None
        self._pending_placement_fi = None
        self._placement_status_msg = None
        self._reopen_ui_state = None
        self._reopen_scroll_offset = None
        self._reopen_layout_pending = False
        self._suppress_tree_events = False
        self._dark_theme = config.load().get("ui_theme", "light") == "dark"
        self._virtual_mode = False
        self._virtual_scroll_gen = 0
        self._virtual_updating = False
        self._last_scroll_width = -1.0
        self._reopen_window_geometry = None
        self._catalog_changing = False
        self._project_family_index = None
        self._project_family_index_doc = None
        self._last_escape_press_at = 0.0
        self._window_gen = 0
        self._window_closing = False
        self._scan_gen = 0
        self._show_catalog_after_scan = False

    def _init_window(self):
        avro_log.event("family_browser", "window_init")
        self._search_timer = None
        self._grid_relayout_timer = None
        self._grid_relayout_gen = 0
        self._last_escape_press_at = 0.0
        self._load_mode = False
        self._window_closing = False
        self._cleanup_done = False
        self._window_gen += 1
        self.win = ui_utils.load_xaml(_THIS_DIR)
        self._restore_window_geometry()
        self._set_revit_window_owner()
        self.ui = ui_utils.NamedUiControls(self.win, _UI_CONTROL_NAMES)
        self._status_controller = family_browser_status.StatusController(self.ui)
        self._library_controller = family_browser_library.LibraryController(self)
        self._card_brushes = ui_theme.card_brushes(
            ui_theme.DARK if self._dark_theme else ui_theme.LIGHT)
        self._props_controller = family_browser_props.PropsPanelController(
            self, self._card_brushes)
        self._bind()
        i18n.init_from_config()
        self._apply_ui_theme(self._dark_theme, persist=False)
        self._apply_language()
        ui_notify.unregister_language_listener(self._on_external_language_changed)
        ui_notify.unregister_theme_listener(self._on_external_theme_changed)
        ui_notify.register_language_listener(self._on_external_language_changed)
        ui_notify.register_theme_listener(self._on_external_theme_changed)
        self.win.SizeChanged += self._on_window_resize
        self.win.Closing += self._on_window_closing
        self._start_project_family_index_build()
        self._publish_pending_loads()

    def _publish_pending_loads(self):
        """Publish data completed while no Family Browser window existed."""
        with self._state_lock:
            initial = self._initial_load_result
            scan_result = self._pending_scan_result
            self._initial_load_result = None
            self._pending_scan_result = None
        if initial is not None:
            if not self._dispatch_current_window(
                    lambda: self._on_initial_load_done(*initial)):
                with self._state_lock:
                    self._initial_load_result = initial
        if scan_result is not None:
            scan, scan_gen, error = scan_result
            if error:
                published = self._dispatch_current_window(
                    lambda msg=error: self._set_status(msg))
            else:
                published = self._dispatch_current_window(
                    lambda value=scan, gen=scan_gen:
                    self._scan_done(value, gen))
            if not published:
                with self._state_lock:
                    self._pending_scan_result = scan_result

    def _dispatch_current_window(self, callback):
        """Queue a UI callback only for the currently live WPF window."""
        win = self.win
        window_gen = self._window_gen
        if win is None:
            return False
        try:
            def guarded_callback():
                if (self._window_closing
                        or not self._window_is_current(win, window_gen)):
                    return
                callback()
            win.Dispatcher.BeginInvoke(System.Action(guarded_callback))
            return True
        except Exception as ex:
            libcache._log(u"ui callback: {}".format(as_unicode(ex)))
            return False

    def _restore_window_geometry(self):
        """Restore the user's window bounds before rebuilding the catalog."""
        geometry = self._reopen_window_geometry
        if not geometry:
            return
        try:
            self.win.WindowStartupLocation = System.Windows.WindowStartupLocation.Manual
            self.win.Width = float(geometry.get("width"))
            self.win.Height = float(geometry.get("height"))
            self.win.Left = float(geometry.get("left"))
            self.win.Top = float(geometry.get("top"))
        except Exception:
            pass

    def _window_is_current(self, win, window_gen):
        return (self.win is win and self.ui is not None
                and window_gen == self._window_gen)

    def _set_revit_window_owner(self):
        """Keep the modeless Family Browser associated with Revit's window."""
        try:
            from System.Windows.Interop import WindowInteropHelper
            handle = revit.uidoc.Application.MainWindowHandle
            if handle:
                WindowInteropHelper(self.win).Owner = handle
        except Exception:
            pass

    def _apply_ui_theme(self, dark, persist=True):
        palette = ui_theme.DARK if dark else ui_theme.LIGHT
        self._dark_theme = dark
        ui_theme.apply_window_theme(self.win, palette)
        _sync_card_colors(palette)
        self._card_brushes = ui_theme.card_brushes(palette)
        if getattr(self, "_props_controller", None) is not None:
            self._props_controller.brushes = self._card_brushes
        self._refresh_cards_theme()
        self._set_load_button_label()
        self._refresh_recent_header()
        if persist:
            config.set_value("ui_theme", "dark" if dark else "light")

    def _apply_language(self):
        if self.ui is None or self.win is None:
            return
        self.win.Title = i18n.t("app_title")
        lbl = getattr(self.ui, "LblFolder", None)
        if lbl is not None:
            lbl.Text = i18n.t("folder_label")
        hint = getattr(self.ui, "SearchHint", None)
        if hint is not None:
            hint.Text = i18n.t("search_placeholder")
        filters_title = getattr(self.ui, "FiltersTitle", None)
        if filters_title is not None:
            filters_title.Text = i18n.t("filters_title")
        btn_clear = getattr(self.ui, "BtnClearSearch", None)
        if btn_clear is not None:
            btn_clear.ToolTip = i18n.t("clear_search_tooltip")
        props_title = getattr(self.ui, "PropsTitle", None)
        if props_title is not None:
            props_title.Text = i18n.t("props_title")
        self._props_controller.reset()
        self._refresh_recent_header()
        self.ui.BtnSettings.Content = i18n.t("btn_library")
        self.ui.BtnSettings.ToolTip = i18n.t("btn_library_tooltip")
        self.ui.BtnReload.Content = i18n.t("btn_reload")
        self.ui.BtnReload.ToolTip = i18n.t("btn_reload_tooltip")
        self._set_load_button_label()
        self._refresh_live_labels()

    def _on_external_language_changed(self):
        if self.ui is None or self.win is None:
            return
        try:
            if not self.win.IsVisible:
                return
        except Exception:
            return
        i18n.init_from_config()
        self._apply_language()

    def _on_external_theme_changed(self):
        if self.ui is None or self.win is None:
            return
        try:
            if not self.win.IsVisible:
                return
        except Exception:
            return
        dark = config.load().get("ui_theme", "light") == "dark"
        self._apply_ui_theme(dark, persist=False)

    def _update_count_display(self, shown, total=None):
        self._status_controller.update_count(shown, total)

    def _update_breadcrumb_display(self):
        if self.ui is None:
            return
        if self._scope_is_recent:
            self._folder_scope_label = i18n.t("recent")
        query = as_unicode(self._active_search_query).strip()
        if query:
            self._set_breadcrumb(
                u"{}{}".format(self._folder_scope_label,
                               i18n.t("search_suffix", q=query)))
        else:
            self._set_breadcrumb(self._folder_scope_label)

    def _refresh_live_labels(self):
        """Re-apply i18n to breadcrumb, count, and folder label after language change."""
        if self.ui is None:
            return
        lbl = getattr(self.ui, "LblFolder", None)
        if lbl is not None:
            lbl.Text = i18n.t("folder_label")
        self._update_breadcrumb_display()
        n = len(self._order_paths) if self._order_paths else 0
        if self._active_search_query.strip():
            total = len(self._folder_scope) if self._folder_scope else n
            self._update_count_display(n, total)
        else:
            self._update_count_display(n)
        self._refresh_status_for_language()
        self._refresh_card_size_labels()

    def _refresh_status_for_language(self):
        n = len(self._order_paths) if self._order_paths else 0
        if n <= 0:
            return
        if getattr(self, "_card_batch_families", None):
            self._set_status(i18n.t("loading_cards", n=n))
            return
        if self._virtual_mode:
            self._set_status(i18n.t("virtual_scroll_hint", n=n))
        else:
            self._set_status(i18n.t("previews_done"))

    def _refresh_card_size_labels(self):
        for card in self._card_by_path.values():
            fi = card.Tag
            if fi is None:
                continue
            sp = card.Child
            if sp is None:
                continue
            for child in sp.Children:
                if not isinstance(child, TextBlock):
                    continue
                if child.FontSize == 10 and child.TextWrapping != TextWrapping.Wrap:
                    child.Text = i18n.t("size_mb").format(fi.size_kb / 1024.0)
                    break

    def _refresh_cards_theme(self):
        for path in self._card_by_path:
            self._set_card_selected(path, path in self._selected_paths)
        for card in self._card_by_path.values():
            sp = card.Child
            if sp is None:
                continue
            for child in sp.Children:
                if not isinstance(child, TextBlock):
                    continue
                if child.TextWrapping == TextWrapping.Wrap:
                    child.Foreground = COL_TEXT
                else:
                    child.Foreground = COL_MUTED

    def _restore_ui_after_reopen(self):
        if not self._scan.get("all"):
            self._set_status(i18n.t("loading_cache"))
            self._publish_pending_loads()
            return
        self._reopen_layout_pending = True
        self._build_tree(self._scan)
        state = self._reopen_ui_state
        self._reopen_ui_state = None
        self._suppress_tree_events = True
        try:
            if state and state.get("label") is not None:
                self._restore_browse_state(state)
                return
            self._show_recents_default()
        finally:
            self._suppress_tree_events = False

    def _restore_browse_state(self, state):
        """Restore folder view and active search after placement."""
        tag = state.get("tree_tag")
        scope = list(state.get("scope") or [])
        label = state.get("label", u"")
        search_query = as_unicode(state.get("search_query", u"")).strip()
        self._reopen_scroll_offset = state.get("scroll_offset")
        try:
            self._reopen_scroll_offset = max(
                0.0, float(self._reopen_scroll_offset))
        except (TypeError, ValueError):
            self._reopen_scroll_offset = None

        if tag == "__recent__":
            self._folder_scope = list(self._recent_families())
            self._scope_is_recent = True
            self._folder_scope_label = i18n.t("recent")
        else:
            self._folder_scope = scope
            self._scope_is_recent = False
            self._folder_scope_label = label
        self._active_search_query = search_query

        if search_query:
            self._stop_search_timer()
            self._search_suppress = True
            try:
                self.ui.SearchBox.Text = search_query
            finally:
                self._search_suppress = False
        else:
            self._reset_search_field()
        self._refresh_catalog_view()

        if tag == "__recent__":
            self._select_recents_tree_item()
        elif tag:
            self._select_tree_item_by_tag(tag)

    def _library_path(self):
        return (self.cfg.get("library_path", "") or "").strip()

    def _library_paths(self):
        """Список из одного пути — для кэша и сканера."""
        p = self._library_path()
        if p and os.path.isdir(p):
            return [p]
        return []

    def _normalize_scan(self, scan):
        """В дереве только одна корневая библиотека из настроек."""
        if not scan:
            return {"roots": [], "all": [], "index": {}}
        path = self._library_path()
        if not path:
            return {"roots": [], "all": [], "index": {}}
        norm_root = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        roots = []
        for node in scan.get("roots", []):
            node_norm = os.path.normcase(
                os.path.normpath(os.path.abspath(node.path)))
            if node_norm == norm_root:
                roots.append(node)
                break
        if not roots:
            return {"roots": [], "all": [], "index": {}}
        root = roots[0]
        scanner.finalize_folder_counts([root])
        all_families = root.descendants()
        return {
            "roots": [root],
            "all": all_families,
            "index": scanner.index_folder_tree([root]),
        }

    def _cache_key(self):
        return _library_cache_key(self._library_paths())

    def _invalidate_project_family_index(self):
        self._project_family_index = None
        self._project_family_index_doc = None

    def _start_project_family_index_build(self):
        """Build the project family index on the UI thread after window init."""
        doc = self.doc
        win = self.win
        gen = self._window_gen
        if doc is None or win is None:
            return

        def build_on_ui():
            if self.win is not win or gen != self._window_gen:
                return
            try:
                self._build_project_family_index_sync()
            except Exception as ex:
                libcache._log(u"family index build: {}".format(as_unicode(ex)))

        try:
            win.Dispatcher.BeginInvoke(System.Action(build_on_ui))
        except Exception as ex:
            libcache._log(u"family index schedule: {}".format(as_unicode(ex)))

    def _store_project_family_index(self, index):
        self._project_family_index = index
        self._project_family_index_doc = self.doc

    def _project_family_index_ready(self):
        return (
            self._project_family_index is not None
            and self._project_family_index_doc is self.doc
        )

    def _build_project_family_index_sync(self):
        if self._project_family_index_ready():
            return self._project_family_index
        idx = {}
        for fam in FilteredElementCollector(self.doc).OfClass(RevitFamily):
            key = family_utils.normalize_family_key(revit_name(fam))
            if key and key not in idx:
                idx[key] = fam
        self._store_project_family_index(idx)
        return idx

    def _persist_cache(self, async_save=False):
        key = self._cache_key()
        if not key or not self._scan.get("all"):
            return
        with self._preview_mem_lock:
            preview_miss = dict(self._preview_miss)
        # The compact sidecar must survive normal Revit shutdown even when
        # the larger library-index save is deferred to a daemon thread.
        libcache.save_preview_misses(key, preview_miss)
        if async_save:
            scan = self._scan
            t = threading.Thread(
                target=self._persist_cache_worker,
                args=(key, scan, preview_miss))
            t.setDaemon(True)
            t.start()
            return
        self._persist_cache_worker(key, self._scan, preview_miss)

    def _persist_cache_worker(self, key, scan, preview_miss=None):
        try:
            saved, msg = libcache.save(key, scan, None)
            _save_sticky_session(key, {}, preview_miss or {})
            if saved:
                config.patch_fields({
                    "library_cache_hash": libcache.key_hash(key),
                    "library_cache_count": len(scan.get("all", [])),
                })
            else:
                libcache._log(u"persist failed: {}".format(msg))
        except Exception as ex:
            libcache._log(u"persist worker: {}".format(as_unicode(ex)))

    def _start_initial_load(self):
        if self._initial_load_started or self._load_state not in ("idle", "error"):
            return
        self._initial_load_started = True
        self._load_state = "loading_cache"
        paths = self._library_paths()
        key = libcache.cache_key(paths)
        libcache._log(u"startup paths={} key={}".format(paths, key))

        def worker():
            scan, disk_miss, err = None, set(), u"no_key"
            try:
                if key and libcache.cache_available(key):
                    scan, disk_miss, err = libcache.load(key)
                    if scan is None:
                        err = err or u"load_failed"
                elif key:
                    err = u"no_cache_file"
            except Exception as ex:
                err = unicode(ex)
                libcache._log(u"startup worker error: {}".format(err))
            result = (scan, disk_miss, err)
            with self._state_lock:
                if self.win is None or self._window_closing:
                    self._initial_load_result = result
                    return
            if not self._dispatch_current_window(
                    lambda: self._on_initial_load_done(*result)):
                with self._state_lock:
                    self._initial_load_result = result

        t = threading.Thread(target=worker)
        t.setDaemon(True)
        t.start()

    def _on_initial_load_done(self, scan, disk_miss, err):
        if self.ui is None or self.win is None:
            with self._state_lock:
                self._initial_load_result = (scan, disk_miss, err)
            return
        if scan is not None:
            self._load_state = "ready"
            libcache._log(u"startup using cache (not scanning folders)")
            self._apply_cache(scan, disk_miss)
            return
        libcache._log(u"startup full scan: {} paths={}".format(
            err, self._library_paths()))
        self._build_tree({"roots": [], "all": [], "index": {}})
        self._show_recents_default()
        if self._library_path():
            self._load_state = "scanning"
            self._set_status(i18n.t("scanning"))
            self._schedule_scan()
            return
        self._load_state = "error"
        self._set_status(i18n.t("cache_not_found"))

    def _apply_cache(self, scan, disk_miss):
        self._set_status(i18n.t("building_tree"))
        self.cfg = config.load()
        sticky_key, sticky_mem, sticky_miss = _load_sticky_session()
        self._scan = self._normalize_scan(scan)
        self._all_fi_by_path = dict(
            (fi.path, fi) for fi in self._scan.get("all", []))
        sk = libcache.cache_key(list(sticky_key)) if sticky_key else None
        if sk == self._cache_key() and sticky_mem:
            with self._preview_mem_lock:
                self._preview_mem = dict(sticky_mem)
                self._preview_order = list(self._preview_mem.keys())
        else:
            with self._preview_mem_lock:
                self._preview_mem = {}
                self._preview_order = []
        # Legacy path-only misses from the full index are intentionally not
        # restored; the validated sidecar is the authoritative source.
        self._restore_preview_misses()

        self._build_tree(self._scan)
        if self._show_catalog_after_scan:
            self._show_catalog_after_scan = False
            self._open_catalog(
                self._scan.get("all", []),
                os.path.basename(os.path.normpath(self._library_path())))
        else:
            self._show_recents_default()
        self._restore_window_focus()

    def _restore_window_focus(self):
        if self.win is None:
            return
        try:
            if self.win.WindowState == System.Windows.WindowState.Minimized:
                self.win.WindowState = System.Windows.WindowState.Normal
        except Exception:
            pass
        try:
            self.win.Activate()
            self.win.Focus()
        except Exception:
            pass
        total = len(self._scan.get("all", []))
        self._set_status(i18n.t("from_cache", n=total))

    def _try_restore_cache(self):
        paths = self._library_paths()
        key = libcache.cache_key(paths)
        libcache._log(u"restore try paths={} key={}".format(paths, key))
        if not key:
            libcache._log(u"restore: no cache key")
            return False
        self._set_status(i18n.t("loading_cache"))
        scan, disk_miss, err = libcache.load(key)
        if scan is None:
            libcache._log(u"restore failed: {} key={}".format(err, key))
            return False
        self._apply_cache(scan, disk_miss)
        return True

    def _on_window_closing(self, sender, e):
        try:
            self._window_closing = True
            self._window_gen += 1
            self._stop_search_timer()
            self._stop_grid_relayout_timer()
            try:
                width = float(self.win.ActualWidth)
                height = float(self.win.ActualHeight)
                if width > 0 and height > 0:
                    self._reopen_window_geometry = {
                        "width": width,
                        "height": height,
                        "left": float(self.win.Left),
                        "top": float(self.win.Top),
                    }
            except Exception:
                pass
            # Placement closes the window and reopens it; async cache save must
            # not overwrite recent_families written right after placement.
            is_placement = (self._pending_symbol_id
                            or self._pending_placement_fi is not None)
            if not is_placement:
                ui_notify.unregister_language_listener(
                    self._on_external_language_changed)
                ui_notify.unregister_theme_listener(
                    self._on_external_theme_changed)
                self._persist_cache(async_save=False)
        except Exception as ex:
            libcache._log(u"window closing: {}".format(as_unicode(ex)))
        finally:
            try:
                self._cleanup_window_resources()
            except Exception as ex:
                libcache._log(u"window cleanup: {}".format(as_unicode(ex)))

    def _cleanup_window_resources(self):
        """Stop window work and release references before WPF teardown."""
        if self._cleanup_done:
            return
        self._cleanup_done = True
        self._preview_gen += 1
        self._scan_gen += 1
        self._grid_relayout_gen += 1
        self._virtual_scroll_gen += 1
        self._card_build_gen += 1
        self._card_batch_families = None
        self._card_batch_index = 0
        self._hover_card = None
        self._preview_worker_lock.acquire()
        try:
            self._preview_pending_request = None
        finally:
            self._preview_worker_lock.release()

        if self._search_timer is not None:
            try:
                self._search_timer.Tick -= self._on_search_debounced
            except Exception:
                pass
            self._search_timer = None
        if self._grid_relayout_timer is not None:
            try:
                self._grid_relayout_timer.Tick -= self._on_grid_relayout_debounced
            except Exception:
                pass
            self._grid_relayout_timer = None

        u = self.ui
        win = self.win
        if u is not None:
            for control, event_name, handler in (
                    (u.SearchBox, "KeyDown", self._on_search_box_keydown),
                    (u.CategoryTree, "SelectedItemChanged", self._on_cat_selected),
                    (u.CategoryTree, "PreviewMouseLeftButtonDown",
                     self._on_tree_preview_mouse_down),
                    (u.FamilyScrollViewer, "ScrollChanged", self._on_family_scroll),
                    (u.FamilyScrollViewer, "SizeChanged",
                     self._on_family_panel_resize),
                    (u.BtnSettings, "Click", self._library_controller.on_settings),
                    (u.BtnReload, "Click", self._library_controller.on_reload),
                    (u.SearchBox, "TextChanged", self._on_search),
                    (getattr(u, "BtnLoad", None), "Click", self._on_btn_load),
                    (getattr(u, "BtnClearSearch", None), "Click",
                     self._on_reset_search)):
                if control is None:
                    continue
                try:
                    event = getattr(control, event_name)
                    event -= handler
                except Exception:
                    pass
            panel = self._family_panel_bound
            if panel is not None:
                try:
                    panel.PreviewMouseDown -= self._on_family_panel_mouse_down
                    panel.PreviewMouseMove -= self._on_family_panel_mouse_move
                    panel.MouseLeave -= self._on_family_panel_mouse_leave
                except Exception:
                    pass
        if win is not None:
            for event_name, handler in (
                    ("PreviewKeyDown", self._on_window_preview_keydown),
                    ("SizeChanged", self._on_window_resize),
                    ("Closing", self._on_window_closing)):
                try:
                    event = getattr(win, event_name)
                    event -= handler
                except Exception:
                    pass

        with self._preview_mem_lock:
            self._preview_mem.clear()
            self._preview_order = []
        # Preview misses belong to the library, not to this temporary window.
        self._card_views.clear()
        self._card_by_path.clear()
        self._fi_by_path.clear()
        self._family_panel_bound = None

    def _on_window_preview_keydown(self, sender, e):
        try:
            if e.IsRepeat:
                return
        except Exception:
            pass

        if e.Key != Key.Escape:
            self._last_escape_press_at = 0.0
            return

        if self._load_mode:
            self._load_mode = False
            self._clear_selection()
            self._anchor_path = None
            self._last_escape_press_at = 0.0
            self._set_load_button_label()
            if self._hover_card is not None:
                self._hover_card.Background = COL_CARD_HOV
            self._set_status(i18n.t("status_ready"))
            e.Handled = True
            return

        now = time.time()
        if ((now - self._last_escape_press_at)
                <= _DOUBLE_ESC_CLOSE_WINDOW_S):
            self._last_escape_press_at = 0.0
            e.Handled = True
            self.win.Close()
            return

        self._last_escape_press_at = now

    def _bind(self):
        u = self.ui
        self.win.PreviewKeyDown            += self._on_window_preview_keydown
        u.SearchBox.KeyDown                += self._on_search_box_keydown
        u.SearchBox.TextChanged            += self._on_search
        u.CategoryTree.SelectedItemChanged += self._on_cat_selected
        u.CategoryTree.PreviewMouseLeftButtonDown += self._on_tree_preview_mouse_down
        u.FamilyScrollViewer.ScrollChanged += self._on_family_scroll
        u.FamilyScrollViewer.SizeChanged   += self._on_family_panel_resize
        u.BtnSettings.Click                += self._library_controller.on_settings
        u.BtnReload.Click                  += self._library_controller.on_reload
        u.BtnLoad.Click                    += self._on_btn_load
        btn_clear = getattr(u, "BtnClearSearch", None)
        if btn_clear is not None:
            btn_clear.Click += self._on_reset_search
        self._props_controller.reset()


    def _set_load_button_label(self):
        """Keep the load button visibly active while selecting families."""
        if self.ui is None:
            return
        btn = getattr(self.ui, "BtnLoad", None)
        if btn is None:
            return
        btn.Content = i18n.t("btn_load")
        if self._load_mode:
            btn.Background = COL_CARD_SEL
            btn.BorderBrush = COL_CARD_SEL_BORDER
            btn.ToolTip = i18n.t("btn_load_tooltip_sel")
        else:
            try:
                btn.ClearValue(Button.BackgroundProperty)
                btn.ClearValue(Button.BorderBrushProperty)
            except Exception:
                btn.Background = COL_CARD
                btn.BorderBrush = COL_BORDER
            btn.ToolTip = i18n.t("btn_load_tooltip")

    def _update_load_selection_status(self):
        self._set_status(
            i18n.t("selected_count", n=len(self._selected_paths)))

    def _on_btn_load(self, sender, e):
        if not self._load_mode:
            self._load_mode = True
            self._clear_selection()
            self._anchor_path = None
            self._set_load_button_label()
            self._update_load_selection_status()
            return

        paths = [path for path in self._order_paths
                 if path in self._selected_paths]
        self._load_mode = False
        self._clear_selection()
        self._anchor_path = None
        self._set_load_button_label()
        if self._hover_card is not None:
            self._hover_card.Background = COL_CARD_HOV
        if paths:
            self._load_families(paths)
        else:
            self._set_status(i18n.t("status_ready"))

    def _on_load_mode_card_click(self, fi, e):
        shift = (Keyboard.Modifiers & ModifierKeys.Shift) == ModifierKeys.Shift
        if shift and self._anchor_path is not None:
            try:
                anchor_i = self._path_to_index[self._anchor_path]
                target_i = self._path_to_index[fi.path]
                start = min(anchor_i, target_i)
                end = max(anchor_i, target_i) + 1
                self._select_paths(self._order_paths[start:end], replace=True)
            except (KeyError, TypeError):
                self._select_paths([fi.path], replace=True)
        else:
            if fi.path in self._selected_paths:
                self._selected_paths.remove(fi.path)
                self._set_card_selected(fi.path, False)
            else:
                self._select_paths([fi.path], replace=False)
            self._anchor_path = fi.path
        self._update_load_selection_status()
        e.Handled = True


    def _host_label(self, key):
        mapping = {
            family_inspector.HOST_CEILING: "host_ceiling",
            family_inspector.HOST_WALL: "host_wall",
            family_inspector.HOST_FLOOR: "host_floor",
            family_inspector.HOST_ROOF: "host_roof",
            family_inspector.HOST_FACE: "host_face",
            family_inspector.HOST_WORK_PLANE: "host_work_plane",
            family_inspector.HOST_INDEPENDENT: "host_independent",
            family_inspector.HOST_UNKNOWN: "host_unknown",
            family_inspector.HOST_OTHER: "host_other",
            family_inspector.HOST_ALL: "filter_all",
        }
        i18n_key = mapping.get(as_unicode(key).lower(), None)
        if i18n_key:
            return i18n.t(i18n_key)
        return as_unicode(key) or i18n.t("host_unknown")

    def _placement_label(self, key):
        k = as_unicode(key or u"")
        if not k or k.lower() == family_inspector.HOST_ALL:
            return i18n.t("filter_all")
        i18n_key = u"placement_" + k
        try:
            text = i18n.t(i18n_key)
            if text and text != i18n_key:
                return text
        except Exception:
            pass
        return k

    def _on_reset_search(self, sender, e):
        self._stop_search_timer()
        self._active_search_query = u""
        self._search_suppress = True
        try:
            self.ui.SearchBox.Text = u""
        finally:
            self._search_suppress = False
        self._refresh_catalog_view()

    def _on_search_box_keydown(self, sender, e):
        try:
            if e.Key == Key.Enter:
                e.Handled = True
                self._stop_search_timer()
                self._apply_search(self.ui.SearchBox.Text)
        except Exception:
            pass

    def _refresh_catalog_view(self):
        """Re-apply the current search query to the folder scope."""
        query = as_unicode(self._active_search_query).strip()
        families = list(self._folder_scope or [])
        if query:
            families = scanner.flat_search(families, query)
        self._show_families(families)
        self._update_breadcrumb_display()
        total = len(self._folder_scope or [])
        shown = len(families)
        if query and total != shown:
            self._update_count_display(shown, total)
        else:
            self._update_count_display(shown)
        self._props_controller.reset()

    def _schedule_scan(self):
        paths = self._library_paths()
        valid = [p for p in paths if os.path.isdir(p)]
        if not valid:
            self._set_status(i18n.t("library_path_required"))
            return
        paths = valid
        self._scan_gen += 1
        avro_log.event("family_browser", "scan_start", {"paths": len(paths)})
        self._set_status(i18n.t("scanning"))
        t = threading.Thread(
            target=self._do_scan,
            args=(list(paths), self._scan_gen, self.win, self._window_gen))
        t.setDaemon(True)
        t.start()

    def _do_scan(self, paths, scan_gen, win, window_gen):
        try:
            def progress(n):
                if scan_gen != self._scan_gen:
                    return
                self._dispatch_current_window(
                    lambda c=n: self._set_status(
                        i18n.t("scanning_progress", n=c)))

            scan = scanner.scan_library(paths, progress_cb=progress)
        except Exception as ex:
            msg = i18n.t("scan_error", err=as_unicode(ex))
            if scan_gen != self._scan_gen:
                return
            self._load_state = "error"
            if self._window_closing or not self._dispatch_current_window(
                    lambda: self._set_status(msg)):
                with self._state_lock:
                    self._pending_scan_result = (None, scan_gen, msg)
            return
        if scan_gen != self._scan_gen:
            return
        if self._window_closing or not self._dispatch_current_window(
                lambda: self._scan_done(scan, scan_gen)):
            with self._state_lock:
                self._pending_scan_result = (scan, scan_gen, None)

    def _scan_done(self, scan, scan_gen=None):
        if scan_gen is not None and scan_gen != self._scan_gen:
            return
        if self.ui is None or self.win is None:
            with self._state_lock:
                self._pending_scan_result = (scan, scan_gen, None)
            return
        self._scan = self._normalize_scan(scan)
        self._all_fi_by_path = dict(
            (fi.path, fi) for fi in self._scan.get("all", []))
        self._load_state = "ready"
        avro_log.event("family_browser", "scan_ready", {
            "families": len(self._scan.get("all", []))})
        total = len(self._scan.get("all", []))
        n_folders = len(self._scan.get("index", {}))
        self._restore_preview_misses()
        self._invalidate_project_family_index()
        self._build_tree(self._scan)
        if self._show_catalog_after_scan:
            self._show_catalog_after_scan = False
            self._open_catalog(
                self._scan.get("all", []),
                os.path.basename(os.path.normpath(self._library_path())))
        else:
            self._show_recents_default()
        self._restore_window_focus()
        t = threading.Thread(
            target=self._save_scan_cache,
            args=(self._scan, scan_gen, self.win, self._window_gen,
                  total, n_folders))
        t.setDaemon(True)
        t.start()

    def _save_scan_cache(self, scan, scan_gen, win, window_gen,
                         total, n_folders):
        key = self._cache_key()
        saved, save_msg = libcache.save(key, scan, None)
        if saved:
            config.patch_fields({
                "library_cache_hash": libcache.key_hash(key),
                "library_cache_count": total,
            })
        if scan_gen != self._scan_gen:
            return
        self._dispatch_current_window(
            lambda: self._cache_save_done(saved, save_msg, total, n_folders))

    def _cache_save_done(self, saved, save_msg, total, n_folders):
        if saved:
            self._set_status(
                i18n.t("loaded_saved", n=total, f=n_folders))
        else:
            self._set_status(i18n.t("loaded_no_cache", n=total))

    def _refresh_recent_header(self):
        tree = getattr(self.ui, "CategoryTree", None) if self.ui else None
        if tree is None:
            return
        for item in tree.Items:
            if getattr(item, "Tag", None) == "__recent__":
                item.Header = i18n.t("recent")
                item.FontWeight = FontWeights.SemiBold
                break

    def _build_tree(self, scan):
        tree = self.ui.CategoryTree
        tree.Items.Clear()

        recent_item = TreeViewItem()
        recent_item.Header = i18n.t("recent")
        recent_item.Tag = "__recent__"
        recent_item.Uid = "TreeRecent"
        recent_item.FontWeight = FontWeights.SemiBold
        tree.Items.Add(recent_item)

        roots = list(scan.get("roots", []))
        for root in roots:
            self._add_folder_node(tree.Items, root, is_root=True,
                                  is_last=(root is roots[-1]))

    def _add_folder_node(self, parent_items, node, is_root=False,
                         is_last=False):
        item = TreeViewItem()
        count = node.count()
        header = u"{} ({})".format(node.name, count)
        item.Header = header
        item.Tag = _TAG_FOLDER_PREFIX + node.path
        item.Uid = "TreeRoot" if is_root else ("TreeLast" if is_last else "")
        item.IsExpanded = is_root
        parent_items.Add(item)

        names = sorted(node.children.keys(), key=lambda s: s.lower())
        for index, name in enumerate(names):
            self._add_folder_node(
                item.Items, node.children[name],
                is_last=(index == len(names) - 1))

    def _stop_search_timer(self):
        if self._search_timer is not None:
            self._search_timer.Stop()

    def _ensure_search_timer(self):
        if self._search_timer is not None:
            return
        timer = DispatcherTimer()
        timer.Interval = System.TimeSpan.FromMilliseconds(_SEARCH_DEBOUNCE_MS)
        timer.Tick += self._on_search_debounced
        self._search_timer = timer

    def _reset_search_field(self):
        self._stop_search_timer()
        self._search_suppress = True
        try:
            self.ui.SearchBox.Text = u""
        finally:
            self._search_suppress = False

    def _recent_families(self):
        """Same order as recent_families.json: last loaded first."""
        self.cfg = config.load()
        by_path = {}
        for fi in self._scan.get("all", []):
            np = libcache._norm_path(fi.path)
            by_path[np] = fi
        ordered = []
        seen = set()
        for p in config.load_recents():
            np = libcache._norm_path(p)
            if np in seen:
                continue
            fi = by_path.get(np)
            if fi is None:
                for fi2 in self._scan.get("all", []):
                    if os.path.normcase(fi2.path) == os.path.normcase(np):
                        fi = fi2
                        break
            if fi is None and os.path.isfile(np):
                try:
                    fi = scanner.FamilyInfo(
                        np, self._library_path() or None)
                except Exception:
                    fi = None
            if fi is not None:
                ordered.append(fi)
                seen.add(np)
        return ordered

    def _current_tree_tag(self):
        item = self.ui.CategoryTree.SelectedItem
        if item is None:
            return None
        return getattr(item, "Tag", None)

    def _select_tree_item_by_tag(self, tag):
        if tag is None:
            return False

        def walk(items, parents):
            for i in range(items.Count):
                item = items[i]
                if getattr(item, "Tag", None) == tag:
                    for p in parents:
                        p.IsExpanded = True
                    item.IsSelected = True
                    item.Focus()
                    return True
                if item.Items.Count and walk(item.Items, parents + [item]):
                    return True
            return False

        return walk(self.ui.CategoryTree.Items, [])

    def _select_recents_tree_item(self):
        tree = self.ui.CategoryTree
        if tree.Items.Count == 0:
            return
        item = tree.Items[0]
        if getattr(item, "Tag", None) == "__recent__":
            item.IsSelected = True
            item.Focus()

    def _show_recents_default(self):
        """Default view on every open: Recent."""
        self._open_catalog(
            self._recent_families(), i18n.t("recent"), is_recent=True)
        self._select_recents_tree_item()

    def _open_catalog(self, families, breadcrumb, is_recent=False):
        """Show a folder catalog; search is limited to these families."""
        self._folder_scope = families
        self._scope_is_recent = is_recent
        self._folder_scope_label = breadcrumb
        self._active_search_query = u""
        self._reset_search_field()
        self._refresh_catalog_view()

    def _on_cat_selected(self, sender, e):
        if self._suppress_tree_events:
            return
        self._open_tree_item(self.ui.CategoryTree.SelectedItem)

    def _open_tree_item(self, item):
        if item is None:
            return
        tag = item.Tag
        if tag == "__recent__":
            self._open_catalog(
                self._recent_families(), i18n.t("recent"), is_recent=True)
        elif tag and tag.startswith(_TAG_FOLDER_PREFIX):
            folder_path = os.path.normpath(tag[len(_TAG_FOLDER_PREFIX):])
            node = self._scan.get("index", {}).get(folder_path)
            if node:
                self._show_folder(node)
            else:
                self._open_catalog([], folder_path, is_recent=False)

    def _on_tree_preview_mouse_down(self, sender, e):
        source = e.OriginalSource
        expander = None
        item = None
        while source is not None:
            if (expander is None and isinstance(source, ToggleButton)
                    and getattr(source, "Name", None) == "Expander"):
                expander = source
            if isinstance(source, TreeViewItem):
                item = source
                break
            try:
                source = VisualTreeHelper.GetParent(source)
            except Exception:
                source = None

        if expander is not None and item is not None:
            item.IsExpanded = not item.IsExpanded
            e.Handled = True
        elif (item is not None and item.IsSelected
              and not self._suppress_tree_events):
            self._open_tree_item(item)
            e.Handled = True

    def _show_folder(self, node):
        breadcrumb = self._folder_breadcrumb(node)
        self._open_catalog(node.descendants(), breadcrumb, is_recent=False)

    def _folder_breadcrumb(self, node):
        parts = []
        path = node.path
        index = self._scan.get("index", {})
        while path and path in index:
            parts.append(index[path].name)
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent
        parts.reverse()
        return u" / ".join(parts)

    def _viewport_width(self):
        """Content width inside ScrollViewer (excludes vertical scrollbar)."""
        sv = self.ui.FamilyScrollViewer
        w = 0.0
        try:
            # Prefer ViewportWidth — already excludes scrollbar track.
            if sv.ViewportWidth and sv.ViewportWidth > 1:
                w = float(sv.ViewportWidth)
            elif sv.ActualWidth and sv.ActualWidth > 1:
                w = float(sv.ActualWidth)
                # If scrollbar is visible, ActualWidth still includes it — subtract.
                try:
                    sb = getattr(sv, "ComputedVerticalScrollBarVisibility", None)
                    from System.Windows import Visibility as _Vis
                    if sb is not None and int(sb) == int(_Vis.Visible):
                        # Standard WPF scrollbar ~17 DIP; keep small equal gutters.
                        w = max(80.0, w - 17.0)
                except Exception:
                    pass
        except Exception:
            w = 0.0
        if w < 80 and self._last_scroll_width > 80:
            w = self._last_scroll_width
        if w < 80 and self.win is not None:
            try:
                width = float(self.win.Width)
            except Exception:
                width = 0.0
            if width > 80:
                w = max(400.0, width - 757.0)
        if w < 80 and self.win is not None:
            w = max(400.0, float(self.win.ActualWidth) - 620.0)
        if w < 80:
            w = 800.0
        return float(w)

    def _layout_metrics(self):
        """Return grid metrics with a fixed, symmetric outer inset."""
        return card_layout.compute_grid_metrics(
            self._viewport_width(),
            min_w=_CARD_MIN_W,
            max_w=_CARD_MAX_W,
            base_w=_CARD_W,
            base_h=_CARD_H,
            margin=_CARD_OUTER_PAD,
        )

    def _layout_cols(self):
        return self._layout_metrics()[0]

    def _card_slot_xy(self, index):
        cols, card_w, card_h, gap, _w, pad_l, pad_tb, _pad_r = self._layout_metrics()
        col = index % cols
        row = index // cols
        x = pad_l + col * (card_w + gap)
        y = pad_tb + row * (card_h + gap)
        return float(x), float(y)

    def _canvas_height_for(self, count):
        if count <= 0:
            return 0.0
        cols, _cw, card_h, gap, _w, _pl, pad_tb, _pr = self._layout_metrics()
        rows = (count + cols - 1) // cols
        # equal outer pad top+bottom; gutters only between rows
        if rows <= 0:
            return 0.0
        return float(2.0 * pad_tb + rows * card_h + max(0, rows - 1) * gap)

    def _on_family_scroll(self, sender, e):
        if self._catalog_changing or not self._virtual_mode:
            return
        self._queue_virtual_sync()

    def _stop_grid_relayout_timer(self):
        if self._grid_relayout_timer is not None:
            self._grid_relayout_timer.Stop()

    def _ensure_grid_relayout_timer(self):
        if self._grid_relayout_timer is not None:
            return
        timer = DispatcherTimer()
        timer.Interval = System.TimeSpan.FromMilliseconds(
            _GRID_RELOAD_DEBOUNCE_MS)
        timer.Tick += self._on_grid_relayout_debounced
        self._grid_relayout_timer = timer

    def _schedule_grid_relayout(self):
        """Rebuild card grid after window/panel resize (coalesced)."""
        if self._catalog_changing or not self._active or self.ui is None:
            return
        if self.win is None:
            return
        self._ensure_grid_relayout_timer()
        self._grid_relayout_timer.Stop()
        self._grid_relayout_timer.Start()

    def _on_grid_relayout_debounced(self, sender, e):
        self._stop_grid_relayout_timer()
        if self._catalog_changing or not self._active or self.ui is None:
            return
        if not hasattr(self, "_grid_relayout_gen"):
            self._grid_relayout_gen = 0
        self._grid_relayout_gen += 1
        gen = self._grid_relayout_gen
        win = self.win
        window_gen = self._window_gen

        def run():
            if (gen != self._grid_relayout_gen
                    or not self._window_is_current(win, window_gen)):
                return
            self._relayout_family_grid()

        if self._window_is_current(win, window_gen):
            win.Dispatcher.BeginInvoke(System.Action(run))

    def _relayout_family_grid(self):
        """Clear visible cards and rebuild layout for current panel width."""
        if not self._active or self.ui is None:
            return
        panel = self.ui.FamilyPanel
        sv = self.ui.FamilyScrollViewer
        cw = sv.ViewportWidth if sv.ViewportWidth > 0 else sv.ActualWidth
        self._last_scroll_width = cw

        panel.Children.Clear()
        self._card_by_path.clear()
        self._card_views.clear()

        if self._virtual_mode:
            n = len(self._active)
            if isinstance(panel, Canvas):
                _cols, _cw, _ch, _gap, vw, _pad_l, _pad_tb, _pad_r = self._layout_metrics()
                panel.Width = vw
                panel.Height = self._canvas_height_for(n)
            self._virtual_sync_viewport()
            return

        for i, fi in enumerate(self._active):
            self._add_family_card(fi, index=i)
        if isinstance(panel, Canvas):
            _cols, _cw, _ch, _gap, vw, _pad_l, _pad_tb, _pad_r = self._layout_metrics()
            panel.Width = vw
            panel.Height = self._canvas_height_for(len(self._active))
        self._preview_gen += 1
        self._schedule_previews(self._active, disk_only=False)

    def _on_window_resize(self, sender, e):
        self._schedule_grid_relayout()

    def _on_family_panel_resize(self, sender, e):
        self._schedule_grid_relayout()

    def _queue_virtual_sync(self):
        self._virtual_scroll_gen += 1
        gen = self._virtual_scroll_gen
        win = self.win
        window_gen = self._window_gen

        def run():
            if (gen != self._virtual_scroll_gen
                    or not self._window_is_current(win, window_gen)):
                return
            self._virtual_sync_viewport()

        if self._window_is_current(win, window_gen):
            win.Dispatcher.BeginInvoke(System.Action(run))

    def _remove_family_card(self, path):
        card = self._card_by_path.pop(path, None)
        self._card_views.pop(path, None)
        if card is not None:
            self.ui.FamilyPanel.Children.Remove(card)

    def _prepare_family_surface(self, virtual):
        """Always use Canvas so the adaptive grid can fill the viewport."""
        sv = self.ui.FamilyScrollViewer
        if not isinstance(sv.Content, Canvas):
            panel = Canvas()
            sv.Content = panel
        else:
            panel = sv.Content
        # Avoid vertical centering gap when canvas is shorter than viewport.
        panel.VerticalAlignment = VerticalAlignment.Top
        panel.HorizontalAlignment = HorizontalAlignment.Left
        panel.Margin = Thickness(0)
        self.ui.FamilyPanel = panel
        if self._family_panel_bound is not panel:
            panel.PreviewMouseDown += self._on_family_panel_mouse_down
            panel.PreviewMouseMove += self._on_family_panel_mouse_move
            panel.MouseLeave += self._on_family_panel_mouse_leave
            self._family_panel_bound = panel
        return panel

    def _card_from_mouse_source(self, source):
        panel = self.ui.FamilyPanel
        current = source
        while current is not None and current is not panel:
            if isinstance(current, Border):
                tag = getattr(current, "Tag", None)
                if tag is not None and hasattr(tag, "path"):
                    return current, tag
            try:
                current = VisualTreeHelper.GetParent(current)
            except Exception:
                return None, None
        return None, None

    def _on_family_panel_mouse_down(self, sender, e):
        if e.ChangedButton not in (
                MouseButton.Left, MouseButton.Right, MouseButton.Middle):
            return
        card, fi = self._card_from_mouse_source(e.OriginalSource)
        if card is None or fi is None:
            return
        if e.ChangedButton == MouseButton.Left:
            if self._load_mode:
                self._on_load_mode_card_click(fi, e)
                return
            self._select_paths([fi.path], replace=True)
            self._on_card_click(card, fi, e)
        elif e.ChangedButton == MouseButton.Right:
            self._on_card_right_click(card, fi, e)
        elif e.ChangedButton == MouseButton.Middle:
            self._on_card_middle_click(card, fi, e)

    def _on_family_panel_mouse_move(self, sender, e):
        card, _fi = self._card_from_mouse_source(e.OriginalSource)
        if card is self._hover_card:
            return
        old = self._hover_card
        self._hover_card = card
        if old is not None:
            old_tag = getattr(old, "Tag", None)
            if old_tag is None or old_tag.path not in self._selected_paths:
                old.Background = COL_CARD
        if card is not None:
            new_tag = getattr(card, "Tag", None)
            if new_tag is not None and new_tag.path not in self._selected_paths:
                card.Background = COL_CARD_HOV

    def _on_family_panel_mouse_leave(self, sender, e):
        if self._hover_card is None:
            return
        old_tag = getattr(self._hover_card, "Tag", None)
        if old_tag is None or old_tag.path not in self._selected_paths:
            self._hover_card.Background = COL_CARD
        self._hover_card = None

    def _force_scroll_top(self):
        """Scroll to top after canvas height changes (small folders after large)."""
        if self.ui is None:
            return
        sv = self.ui.FamilyScrollViewer
        panel = self.ui.FamilyPanel
        try:
            panel.UpdateLayout()
            sv.UpdateLayout()
            sv.ScrollToVerticalOffset(0)
            if hasattr(sv, "ScrollToHome"):
                sv.ScrollToHome()
            sv.UpdateLayout()
            sv.ScrollToVerticalOffset(0)
        except Exception:
            pass

    def _finish_family_view_layout(self):
        """Reset scroll after layout — fixes grid offset after large folders."""
        run_virtual = self._virtual_mode
        win = self.win
        window_gen = self._window_gen

        def done():
            if not self._window_is_current(win, window_gen):
                return
            if self._reopen_scroll_offset is None:
                self._force_scroll_top()
            self._catalog_changing = False
            if run_virtual:
                self._reopen_layout_pending = False
                self._virtual_sync_viewport()
            elif self._reopen_layout_pending:
                self._reopen_layout_pending = False
                self._relayout_family_grid()
            saved_offset = self._reopen_scroll_offset
            self._reopen_scroll_offset = None
            if saved_offset is not None:
                self._restore_scroll_offset(saved_offset)

        if self._window_is_current(win, window_gen):
            from System.Windows.Threading import DispatcherPriority
            win.Dispatcher.BeginInvoke(
                System.Action(done), DispatcherPriority.Loaded)

    def _restore_scroll_offset(self, offset):
        if self.ui is None:
            return
        try:
            sv = self.ui.FamilyScrollViewer
            sv.ScrollToVerticalOffset(max(0.0, float(offset)))
            if self._virtual_mode:
                self._virtual_sync_viewport()
        except Exception:
            pass

    def _virtual_sync_viewport(self):
        if not self._virtual_mode or not self._active:
            return
        families = self._active
        n = len(families)
        if n == 0:
            return

        sv = self.ui.FamilyScrollViewer
        panel = self.ui.FamilyPanel

        cols, card_w, card_h, gap, vw, pad_l, pad_tb, pad_r = self._layout_metrics()
        row_h = float(card_h + gap)
        total_rows = (n + cols - 1) // cols
        canvas_h = self._canvas_height_for(n)
        self._virtual_updating = True
        try:
            panel.Width = vw
            panel.Height = canvas_h
            if self._reopen_scroll_offset is not None:
                sv.ScrollToVerticalOffset(self._reopen_scroll_offset)
        finally:
            self._virtual_updating = False

        view_h = sv.ViewportHeight if sv.ViewportHeight > 0 else 600.0
        scroll_y = sv.VerticalOffset
        max_scroll = max(0.0, canvas_h - view_h)
        if scroll_y > max_scroll + 2.0:
            scroll_y = 0.0
            self._virtual_updating = True
            try:
                sv.ScrollToVerticalOffset(0.0)
            except Exception:
                pass
            finally:
                self._virtual_updating = False

        # Account for equal outer top pad when mapping scroll Y → row index.
        y0 = max(0.0, float(scroll_y) - float(pad_tb))
        y1 = max(0.0, float(scroll_y) + float(view_h) - float(pad_tb))
        first_row = max(0, int(y0 / row_h) - _VIRTUAL_ROW_BUFFER)
        last_row = min(
            total_rows,
            int(y1 / row_h) + _VIRTUAL_ROW_BUFFER + 1)
        first_i = first_row * cols
        last_i = min(n, last_row * cols)
        if first_i >= last_i:
            first_i = 0
            last_i = min(n, cols * (last_row - first_row + 1))
            if last_i <= 0:
                last_i = min(n, cols)

        if last_i - first_i > _VIRTUAL_ITEM_LIMIT:
            visible_first = max(0, int(y0 / row_h) * cols)
            visible_last = min(
                n, (int(y1 / row_h) + 1) * cols)
            visible_count = visible_last - visible_first
            if visible_count > _VIRTUAL_ITEM_LIMIT:
                first_i = visible_first
                last_i = visible_last
            else:
                first_i = max(
                    0, min(visible_first, n - _VIRTUAL_ITEM_LIMIT))
                last_i = min(n, first_i + _VIRTUAL_ITEM_LIMIT)

        wanted = set()
        for i in range(first_i, last_i):
            wanted.add(families[i].path)

        for path in list(self._card_by_path.keys()):
            if path not in wanted:
                self._remove_family_card(path)

        for i in range(first_i, last_i):
            fi = families[i]
            if fi.path in self._card_by_path:
                card = self._card_by_path[fi.path]
                preview_img = self._card_views.get(fi.path)
                if preview_img is not None:
                    _apply_card_metrics(card, preview_img, card_w, card_h)
                else:
                    card.Width = card_w
                    card.Height = card_h
                x, y = self._card_slot_xy(i)
                Canvas.SetLeft(card, x)
                Canvas.SetTop(card, y)
            else:
                self._add_family_card(fi, index=i)

        visible = [families[i] for i in range(first_i, last_i)]
        self._preview_gen += 1
        self._schedule_previews(visible, disk_only=False)

    def _add_family_card(self, fi, index=None):
        panel = self.ui.FamilyPanel
        with self._preview_mem_lock:
            preview = self._preview_mem.get(fi.path)
            if preview is not None:
                if fi.path in self._preview_order:
                    self._preview_order.remove(fi.path)
                self._preview_order.append(fi.path)
        if preview is not None:
            fi.preview = preview
        _cols, card_w, card_h, _gap, _vw, _pad_l, _pad_tb, _pad_r = self._layout_metrics()
        card, preview_img = _make_card(fi, self, card_w=card_w, card_h=card_h)
        self._fi_by_path[fi.path] = fi
        self._card_views[fi.path] = preview_img
        self._card_by_path[fi.path] = card
        if isinstance(panel, Canvas):
            if index is None:
                index = self._path_to_index.get(fi.path)
            if index is not None:
                x, y = self._card_slot_xy(index)
                Canvas.SetLeft(card, x)
                Canvas.SetTop(card, y)
        panel.Children.Add(card)
        if fi.path in self._selected_paths:
            self._set_card_selected(fi.path, True)

    def _show_families(self, families):
        self._stop_grid_relayout_timer()
        self._catalog_changing = True
        self._active = families
        self._card_build_gen += 1
        gen = self._card_build_gen
        self._preview_gen += 1
        self._virtual_scroll_gen += 1
        self._virtual_mode = len(families) > _VIRTUAL_THRESHOLD

        panel = self._prepare_family_surface(self._virtual_mode)
        panel.Children.Clear()
        if isinstance(panel, Canvas):
            panel.Height = 0
            try:
                panel.Width = self._viewport_width()
            except Exception:
                pass
        if self._reopen_scroll_offset is None:
            try:
                self.ui.FamilyScrollViewer.ScrollToVerticalOffset(0)
            except Exception:
                pass
        self._card_views = {}
        self._card_by_path = {}
        self._fi_by_path = {}
        self._order_paths = [fi.path for fi in families]
        self._path_to_index = dict(
            (fi.path, i) for i, fi in enumerate(families))
        self._selected_paths = set()
        self._anchor_path = None
        self._props_controller.reset()

        n = len(families)
        self._update_count_display(n)
        if not families:
            self._virtual_mode = False
            self._catalog_changing = False
            return

        if self._virtual_mode:
            for fi in families:
                self._fi_by_path[fi.path] = fi
            self._set_status(i18n.t("virtual_scroll_hint", n=n))
            self._queue_virtual_sync()
            self._finish_family_view_layout()
            return

        if n <= _CARD_UI_BATCH_THRESHOLD:
            for i, fi in enumerate(families):
                self._add_family_card(fi, index=i)
            if isinstance(panel, Canvas):
                panel.Width = self._viewport_width()
                panel.Height = self._canvas_height_for(n)
            if self._reopen_scroll_offset is None:
                self._force_scroll_top()
            self._schedule_previews(
                families, disk_only=self._browse_disk_only)
            self._finish_family_view_layout()
            return

        self._card_batch_families = list(families)
        self._card_batch_index = 0
        self._card_batch_gen = gen
        self._set_status(i18n.t("loading_cards", n=n))
        self._add_card_batch()

    def _add_card_batch(self, expected_win=None, expected_window_gen=None):
        if (self._card_batch_gen != self._card_build_gen
                or (expected_win is not None
                    and not self._window_is_current(
                        expected_win, expected_window_gen))):
            return
        families = self._card_batch_families
        total = len(families)
        start = self._card_batch_index
        end = min(start + _CARD_UI_BATCH, total)
        batch_started = time.time()
        for i in range(start, end):
            self._add_family_card(families[i], index=i)
            if (time.time() - batch_started) >= _CARD_UI_BUDGET_S:
                end = i + 1
                break
        self._card_batch_index = end
        panel = self.ui.FamilyPanel
        if isinstance(panel, Canvas):
            panel.Width = self._viewport_width()
            panel.Height = self._canvas_height_for(total)
        if end < total:
            self._set_status(
                i18n.t("loading_cards_progress", done=end, total=total))
            win = self.win
            window_gen = self._window_gen
            if self._window_is_current(win, window_gen):
                win.Dispatcher.BeginInvoke(
                    System.Action(
                        lambda: self._add_card_batch(win, window_gen)))
            return
        self._card_batch_families = None
        self._schedule_previews(
            families, disk_only=self._browse_disk_only)
        self._finish_family_view_layout()

    def _schedule_previews(self, families, disk_only=False):
        if self._window_closing or self.win is None:
            return
        self._preview_gen += 1
        gen = self._preview_gen
        win = self.win
        window_gen = self._window_gen
        if not families:
            return
        try:
            self._set_status(i18n.t("previews_progress", done=0,
                                    total=len(families)))
        except Exception:
            pass
        request = (list(families), disk_only)
        self._preview_worker_lock.acquire()
        try:
            if self._preview_worker_running:
                self._preview_pending_request = request
                return
            self._preview_worker_running = True
        finally:
            self._preview_worker_lock.release()
        paths = [fi.path for fi in families]
        total = len(paths)
        done = [0]
        loaded = [0]
        pending = []
        last_status_at = [0.0]

        def flush_pending():
            if (not pending or gen != self._preview_gen
                    or self.win is not win
                    or window_gen != self._window_gen):
                pending[:] = []
                return
            batch = list(pending)
            pending[:] = []
            try:
                win.Dispatcher.BeginInvoke(
                    System.Action(
                        lambda items=batch: self._apply_preview_batch(
                            items, gen, win, window_gen)))
            except Exception as ex:
                libcache._log(u"preview dispatch: {}".format(as_unicode(ex)))

        def worker():
            try:
                for path in paths:
                    if (gen != self._preview_gen
                            or self.win is not win
                            or window_gen != self._window_gen):
                        return
                    with self._preview_mem_lock:
                        preview_loaded = path in self._preview_mem
                        miss = self._preview_miss.get(path)
                    if preview_loaded:
                        done[0] += 1
                        continue
                    if miss is not None:
                        current = self._file_signature(path)
                        if current == miss:
                            done[0] += 1
                            continue
                        with self._preview_mem_lock:
                            self._preview_miss.pop(path, None)
                    extraction_completed = False
                    if not disk_only and gen == self._preview_gen:
                        msg = i18n.t("previews_extracting")
                        try:
                            win.Dispatcher.BeginInvoke(
                                System.Action(
                                    lambda m=msg: self._set_preview_status(
                                        m, win, window_gen, gen)))
                        except Exception:
                            pass
                    try:
                        if disk_only:
                            png = rfa_preview.read_cached_png_bytes(path)
                        else:
                            png = rfa_preview.extract_preview_png_bytes(path)
                            extraction_completed = True
                    except Exception as ex:
                        png = None
                        libcache._log(u"preview file {}: {}".format(
                            path, as_unicode(ex)))
                    done[0] += 1
                    current_request = (
                        gen == self._preview_gen and self.win is win
                        and window_gen == self._window_gen)
                    if png and current_request:
                        with self._preview_mem_lock:
                            self._preview_miss.pop(path, None)
                    elif extraction_completed and current_request:
                        signature = self._file_signature(path)
                        if signature is not None:
                            with self._preview_mem_lock:
                                self._preview_miss[path] = signature
                    if png and gen == self._preview_gen:
                        loaded[0] += 1
                        pending.append((path, png))
                        flush_batch = (5 if self._virtual_mode
                                       else _PREVIEW_FLUSH_BATCH)
                        if (len(pending) >= flush_batch
                                or time.time() - last_status_at[0]
                                >= _PREVIEW_STATUS_INTERVAL_S):
                            flush_pending()
                    if done[0] == total:
                        flush_pending()
                    now = time.time()
                    if (gen == self._preview_gen
                            and self.win is win
                            and window_gen == self._window_gen
                            and now - last_status_at[0]
                            >= _PREVIEW_STATUS_INTERVAL_S):
                        msg = i18n.t("previews_progress",
                                       done=done[0], total=total)
                        last_status_at[0] = now
                        try:
                            win.Dispatcher.BeginInvoke(
                                System.Action(
                                    lambda m=msg: self._set_preview_status(
                                        m, win, window_gen, gen)))
                        except Exception as ex:
                            libcache._log(
                                u"preview progress dispatch: {}".format(
                                    as_unicode(ex)))
                flush_pending()
                if (gen == self._preview_gen
                        and self.win is win
                        and window_gen == self._window_gen):
                    msg = i18n.t("previews_done")
                    try:
                        win.Dispatcher.BeginInvoke(
                            System.Action(
                                lambda m=msg: self._set_preview_status(
                                    m, win, window_gen, gen)))
                    except Exception as ex:
                        libcache._log(
                            u"preview completion dispatch: {}".format(
                                as_unicode(ex)))
            except Exception as ex:
                libcache._log(u"preview worker: {}".format(as_unicode(ex)))
            finally:
                self._preview_worker_lock.acquire()
                try:
                    self._preview_worker_running = False
                    self._preview_worker_thread = None
                    pending_request = self._preview_pending_request
                    self._preview_pending_request = None
                finally:
                    self._preview_worker_lock.release()
                if (pending_request is not None and not self._window_closing
                        and self.win is win
                        and window_gen == self._window_gen):
                    self._schedule_previews(*pending_request)

        t = threading.Thread(target=worker)
        t.setDaemon(True)
        self._preview_worker_thread = t
        t.start()

    def _set_preview_status(self, message, win, window_gen,
                            preview_gen=None):
        if (self.win is not win or window_gen != self._window_gen
                or self.ui is None):
            return
        if preview_gen is not None and preview_gen != self._preview_gen:
            return
        try:
            self._set_status(message)
        except Exception as ex:
            libcache._log(u"preview status: {}".format(as_unicode(ex)))

    def _apply_preview_batch(self, items, gen, win=None, window_gen=None):
        if (win is not None
                and (self.win is not win
                     or window_gen != self._window_gen
                     or self.ui is None)):
            return
        for path, png_bytes in items:
            try:
                self._apply_preview_png(path, png_bytes, gen)
            except Exception as ex:
                libcache._log(u"preview apply: {}".format(as_unicode(ex)))

    def _apply_preview_png(self, path, png_bytes, gen):
        if gen != self._preview_gen:
            return
        try:
            bmp = image_utils.bitmap_from_png_bytes(png_bytes)
        except Exception as ex:
            libcache._log(u"preview bitmap: {}".format(as_unicode(ex)))
            return
        if bmp is None:
            return
        with self._preview_mem_lock:
            self._preview_mem[path] = bmp
            if path in self._preview_order:
                self._preview_order.remove(path)
            self._preview_order.append(path)
            if len(self._preview_mem) > _PREVIEW_MEM_LIMIT:
                visible = set(self._card_views.keys())
                for old_path in list(self._preview_order):
                    if len(self._preview_mem) <= _PREVIEW_MEM_LIMIT:
                        break
                    if old_path in visible or old_path == path:
                        continue
                    del self._preview_mem[old_path]
                    self._preview_order.remove(old_path)
                    old_fi = self._all_fi_by_path.get(old_path)
                    if old_fi is not None:
                        old_fi.preview = None
        preview_img = self._card_views.get(path)
        if preview_img is None:
            return
        fi = self._fi_by_path.get(path)
        if fi is not None:
            fi.preview = bmp
        try:
            preview_img.Source     = bmp
            preview_img.Visibility = Visibility.Visible
        except Exception as ex:
            libcache._log(u"preview image: {}".format(as_unicode(ex)))

    def _set_card_selected(self, path, selected):
        card = self._card_by_path.get(path)
        if card is None:
            return
        if selected:
            card.Background = COL_CARD_SEL
            card.BorderBrush = COL_CARD_SEL_BORDER
        else:
            card.Background = COL_CARD
            card.BorderBrush = COL_BORDER

    def _clear_selection(self):
        for path in list(self._selected_paths):
            self._set_card_selected(path, False)
        self._selected_paths.clear()

    def _select_paths(self, paths, replace=True):
        if replace:
            self._clear_selection()
        for path in paths:
            if (path not in self._fi_by_path
                    and path not in self._order_paths):
                continue
            self._selected_paths.add(path)
            self._set_card_selected(path, True)

    def _reveal_in_explorer(self, fi):
        path = libcache._norm_path(fi.path)
        if not path or not os.path.isfile(path):
            self._set_status(
                i18n.t("file_not_found", name=as_unicode(fi.name)))
            return
        try:
            from System.Diagnostics import Process
            Process.Start(
                "explorer.exe",
                '/select,"{}"'.format(path.replace(u'"', u"")))
            self._set_status(
                i18n.t("explorer_opened", name=as_unicode(fi.name)))
        except Exception as ex:
            self._set_status(
                i18n.t("explorer_failed", err=as_unicode(ex)))

    def _on_card_right_click(self, card, fi, e):
        if not self._load_mode:
            self._select_paths([fi.path], replace=True)
        self._props_controller.inspect(fi)
        e.Handled = True

    def _on_card_middle_click(self, card, fi, e):
        self._reveal_in_explorer(fi)
        e.Handled = True

    def _on_card_click(self, card, fi, e):
        self._place_family(fi)

    def _apply_search(self, query):
        query = as_unicode(query).strip()
        self._active_search_query = query
        self._refresh_catalog_view()

    def _on_search_debounced(self, sender, e):
        self._stop_search_timer()
        if self._search_suppress or self.ui is None:
            return
        self._apply_search(self.ui.SearchBox.Text)

    def _on_search(self, sender, e):
        if self._search_suppress:
            return
        self._ensure_search_timer()
        self._search_timer.Stop()
        self._search_timer.Start()

    def _find_family_in_project(self, fi):
        keys = set(
            family_utils.normalize_family_key(name)
            for name in family_utils.family_name_candidates(fi))
        keys.discard(u"")
        if not keys:
            return None
        file_key = family_utils.normalize_family_key(fi.name)
        best = None
        for fam in FilteredElementCollector(self.doc).OfClass(RevitFamily):
            fam_key = family_utils.normalize_family_key(revit_name(fam))
            if fam_key in keys:
                return fam
            if (file_key and len(file_key) >= 4
                    and (file_key in fam_key or fam_key in file_key)):
                best = fam
        return best

    def _load_family_element(self, fi):
        """Return (Family, error_message, state) for a family load attempt."""
        path = os.path.normpath(fi.path)
        if not os.path.isfile(path):
            return None, i18n.t("file_not_found_short"), "error"
        family_release = self._release_number(
            getattr(fi, "revit_version", u""))
        host_release = self._release_number(self._current_revit_label())
        if (family_release is not None and host_release is not None
                and family_release > host_release):
            return None, i18n.t(
                "newer_version",
                ver=as_unicode(getattr(fi, "revit_version", u"")),
                cur=self._current_revit_label()), "error"

        existing = self._find_family_in_project(fi)

        try:
            fam_ref = clr.Reference[RevitFamily]()
            if (self.doc.LoadFamily(
                    path, family_load_options.FAMILY_LOAD_OPTIONS, fam_ref)
                    and fam_ref.Value is not None):
                state = "already_loaded" if existing is not None else "loaded"
                return fam_ref.Value, None, state
        except Exception as ex:
            return None, as_unicode(ex), "error"
        if existing is not None:
            return existing, None, "already_loaded"
        ver = as_unicode(getattr(fi, "revit_version", u"") or u"")
        hint = i18n.t("load_hint_ver", ver=ver) if ver else u""
        return None, i18n.t("load_failed", hint=hint), "error"

    def _get_placeable_symbol(self, family, fi=None):
        symbols = self._symbols_for_family(family)
        if not symbols:
            return None
        if fi is not None:
            want = family_utils.normalize_family_key(fi.name)
            for sym in symbols:
                if family_utils.normalize_family_key(revit_name(sym)) == want:
                    return sym
        for sym in symbols:
            if sym.IsActive:
                return sym
        return symbols[0]

    def _symbols_for_family(self, family):
        symbols = []
        try:
            ids = family.GetFamilySymbolIds()
            for sid in ids:
                sym = self.doc.GetElement(sid)
                if sym is not None:
                    symbols.append(sym)
        except Exception:
            pass
        return symbols

    def _activate_symbol(self, symbol):
        if symbol is None or symbol.IsActive:
            return
        t = Transaction(self.doc, i18n.t("txn_activate"))
        t.Start()
        try:
            symbol.Activate()
            t.Commit()
        except Exception:
            self._rollback_transaction(t, "activate")
            raise

    def _rollback_transaction(self, transaction, operation):
        try:
            transaction.RollBack()
        except Exception as ex:
            libcache._log(u"rollback {}: {}".format(
                operation, as_unicode(ex)))

    def _get_family_symbol_single(self, fi):
        """Load a family once and return an activated symbol."""
        t = Transaction(self.doc, i18n.t("txn_load"))
        t.Start()
        try:
            fam, err, state = self._load_family_element(fi)
            if fam is None:
                raise Exception(err or u"LoadFamily failed")
            symbol = self._get_placeable_symbol(fam, fi)
            if symbol is None:
                raise Exception(i18n.t("no_symbol", name=revit_name(fam)))
            if not symbol.IsActive:
                symbol.Activate()
            t.Commit()
            self._invalidate_project_family_index()
            return symbol
        except Exception:
            self._rollback_transaction(t, "load")
            raise

    def _place_family(self, fi):
        family_release = self._release_number(
            getattr(fi, "revit_version", u""))
        host_label = self._current_revit_label()
        host_release = self._release_number(host_label)
        if (family_release is not None and host_release is not None
                and family_release > host_release):
            self._set_status(i18n.t(
                "newer_version",
                ver=as_unicode(getattr(fi, "revit_version", u"")),
                cur=host_label))
            return
        uidoc = revit.uidoc
        if uidoc is None or uidoc.ActiveView is None:
            self._set_status(i18n.t("no_active_view"))
            return
        search_query = u""
        scroll_offset = 0.0
        if self.ui is not None:
            search_query = as_unicode(self.ui.SearchBox.Text).strip()
            try:
                scroll_offset = float(
                    self.ui.FamilyScrollViewer.VerticalOffset)
            except (TypeError, ValueError):
                pass
        self._reopen_ui_state = {
            "scope": list(self._folder_scope),
            "label": self._folder_scope_label,
            "tree_tag": self._current_tree_tag(),
            "search_query": search_query,
            "scroll_offset": scroll_offset,
        }
        self._pending_placement_fi = fi
        self._pending_family_name = as_unicode(fi.name)
        self._pending_family_path = libcache._norm_path(fi.path)
        config.add_recent(self._pending_family_path)
        self.cfg = config.load()
        self.win.Close()

    def _run_pending_placement(self, fi):
        uidoc = revit.uidoc
        if uidoc is None or uidoc.ActiveView is None or fi is None:
            return u""
        last_error = None
        avro_log.event("family_browser", "placement_start")
        try:
            symbol = self._get_family_symbol_single(fi)
            if symbol is not None:
                return self._prompt_place_family(uidoc, symbol, fi)
        except Exception as ex:
            last_error = ex

        try:
            fam = self._find_family_in_project(fi)
            if fam is not None:
                symbol = self._get_placeable_symbol(fam, fi)
                if symbol is not None:
                    self._activate_symbol(symbol)
                    return self._prompt_place_family(uidoc, symbol, fi)
        except Exception as ex:
            last_error = ex

        return i18n.t("placement_error", err=as_unicode(last_error))

    def _prompt_place_family(self, uidoc, symbol, fi):
        try:
            uidoc.PromptForFamilyInstancePlacement(symbol)
        except OperationCanceledException:
            return i18n.t("placement_cancelled")
        return i18n.t("placed", name=fi.name)

    def _load_families(self, paths):
        t = None
        loaded = []
        loaded_paths = []
        skipped = []
        errors = []
        label = (paths[0] if len(paths) == 1
                 else i18n.t("load_batch_label", n=len(paths)))
        try:
            t = Transaction(self.doc,
                            i18n.t("txn_load_family", label=label))
            t.Start()
            for path in paths:
                fi = self._fi_by_path.get(path)
                if fi is None:
                    for active_fi in self._active:
                        if active_fi.path == path:
                            fi = active_fi
                            break
                if fi is None:
                    continue
                try:
                    fam, err, state = self._load_family_element(fi)
                    if fam is not None:
                        if state == "already_loaded":
                            skipped.append(fi.name)
                        else:
                            loaded.append(fi.name)
                            loaded_paths.append(fi.path)
                    elif err:
                        errors.append(u"{}: {}".format(fi.name, err))
                    else:
                        skipped.append(fi.name)
                except Exception as ex:
                    errors.append(u"{}: {}".format(fi.name, as_unicode(ex)))
            if loaded or skipped:
                t.Commit()
                for path in loaded_paths:
                    config.add_recent(path)
                self.cfg = config.load()
            else:
                self._rollback_transaction(t, "batch_load_empty")
        except Exception as ex:
            if t is not None:
                self._rollback_transaction(t, "batch_load")
            self._set_status(i18n.t("error_generic", err=as_unicode(ex)))
            return

        parts = []
        if loaded:
            parts.append(i18n.t("loaded_n", n=len(loaded)))
        if skipped and not loaded:
            parts.append(i18n.t("already_in_project", n=len(skipped)))
        if errors:
            parts.append(i18n.t("not_loaded", n=len(errors)))
        self._set_status(
            u"  |  ".join(parts) if parts else i18n.t("done"))

    def _set_status(self, text):
        self._status_controller.set_status(text)

    def _set_breadcrumb(self, text):
        self._status_controller.set_breadcrumb(text)

    def show(self):
        i18n.init_from_config()
        ribbon_i18n.init_from_config()
        avro_log.event("family_browser", "show_start")
        first_open = True
        try:
            while True:
                self._init_window()
                if first_open:
                    self._set_status(i18n.t("opening"))
                    self._start_initial_load()
                    first_open = False
                else:
                    i18n.init_from_config()
                    self._apply_language()
                    self._restore_ui_after_reopen()
                    if self._placement_status_msg:
                        self._set_status(self._placement_status_msg)
                        self._placement_status_msg = None

                try:
                    self.win.ShowDialog()
                except Exception as ex:
                    libcache._log(u"show dialog: {}".format(as_unicode(ex)))
                    break

                # Closing invalidates the preview generation. Let an in-flight
                # extraction leave before returning control to Revit's ribbon.
                preview_thread = self._preview_worker_thread
                if preview_thread is not None and preview_thread is not threading.currentThread():
                    preview_thread.join(10.0)

                pending_id = self._pending_symbol_id
                pending_fi = self._pending_placement_fi
                self._pending_symbol_id = None
                self._pending_placement_fi = None
                self._pending_family_name = u""
                self._pending_family_path = None
                self.win = None
                self.ui = None

                if pending_fi is None and not pending_id:
                    break

                if pending_fi is not None:
                    self._placement_status_msg = self._run_pending_placement(pending_fi)
                else:
                    self._placement_status_msg = self._run_pending_placement(None)
                # PromptForFamilyInstancePlacement has returned; reopen directly.
        finally:
            self._window_closing = True
            ui_notify.unregister_language_listener(
                self._on_external_language_changed)
            ui_notify.unregister_theme_listener(
                self._on_external_theme_changed)
            try:
                if self.win is not None:
                    self._cleanup_window_resources()
            except Exception as ex:
                libcache._log(u"show cleanup: {}".format(as_unicode(ex)))
            self.win = None
            self.ui = None
            avro_log.event("family_browser", "show_end")


# ---------------------------------------------------------------------------
# pyRevit entry — runs when the button is clicked
# ---------------------------------------------------------------------------
dlg = FamilyBrowserDialog()
dlg.show()
