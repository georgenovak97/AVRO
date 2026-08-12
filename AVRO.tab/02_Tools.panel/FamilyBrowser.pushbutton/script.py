# -*- coding: utf-8 -*-
"""
Family Browser — pyRevit extension (AVRO)
Entry point script.
"""
import os
import sys
import threading
import tempfile
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
    MessageBox, MessageBoxButton, MessageBoxImage,
    TextWrapping, FontWeights,
)
from System.Windows.Controls import (
    TreeViewItem, Border, StackPanel, TextBlock, Image, Canvas, ScrollViewer,
    WrapPanel, ComboBox, ComboBoxItem, CheckBox,
)
from System.Windows.Media import SolidColorBrush, Color, Stretch
from System.Windows.Input import Keyboard, ModifierKeys, Key
from System.Windows.Controls import Orientation
from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption
from System.IO import MemoryStream
from System.Windows.Forms import FolderBrowserDialog, DialogResult
from System.Windows.Threading import DispatcherTimer
import Autodesk.Revit.DB as RDB
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    Family as RevitFamily,
    FamilySymbol as RevitFamilySymbol,
    Element as RevitElement,
    Transaction,
    ElementId,
    IFamilyLoadOptions,
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
import rfa_version
import library_cache as libcache
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
import family_browser_status
import family_browser_library
import family_browser_quality
from revit_utils import as_unicode, revit_name, symbol_family

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
    "SearchBox", "SearchHint", "LblFolder",
    "FiltersTitle", "FiltersCount", "BtnResetFilters", "BtnApplyFilters",
    "LblCategoryFilter", "CategoryFilterList",
    "LblHostFilter", "HostFilterList",
    "LblPlacementFilter", "PlacementFilterList",
    "LblVersionFilter", "VersionFilterList",
    "LblImportedFilter", "ImportedFilterList",
    "LblSharedNestedFilter", "SharedNestedFilterList",
    "LblSharedFamilyFilter", "SharedFamilyFilterList",
    "BtnRunSearch", "BtnResetSearch",
    "PropsTitle", "PropsHint", "PropsPanel",
    "CategoryTree", "BtnSettings", "BtnReload",
    "BtnLoadSelected", "FamilyPanel", "FamilyScrollViewer",
    "BreadcrumbText", "CountText", "StatusText",
]


# ---------------------------------------------------------------------------
# Load XAML
# ---------------------------------------------------------------------------
_TAG_FOLDER_PREFIX = "folder:"
# Build medium folder grids in UI batches so the window stays responsive.
_CARD_UI_BATCH = 80
_CARD_UI_BATCH_THRESHOLD = 100
# Above this count only visible cards are created (virtual scroll).
_VIRTUAL_THRESHOLD = 250
_VIRTUAL_ROW_BUFFER = 2
_SEARCH_DEBOUNCE_MS = 400
_GRID_RELOAD_DEBOUNCE_MS = 80
_DOUBLE_ESC_CLOSE_WINDOW_S = 0.6
_CARD_MARGIN = 10
_CARD_W = 156
_CARD_H = 182
_CARD_MIN_W = 132
_CARD_MAX_W = 220
_PREVIEW_W = 96
_PREVIEW_H = 67
_STICKY_KEY = "AVRO_session"


def _library_cache_key(paths):
    return libcache.cache_key(paths)


def clear_library_cache():
    libcache.clear()
    _save_sticky_session(None, {}, set())
    try:
        config.patch_fields({
            "library_cache_hash": "",
            "library_cache_count": 0,
        })
    except Exception:
        pass


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
        return sk, data.get("preview_mem", {}), set(data.get("preview_miss", []))
    except Exception:
        return None, {}, set()


def _save_sticky_session(key, preview_mem, preview_miss):
    try:
        payload = None
        if key is not None:
            payload = {
                "key": list(key),
                "preview_mem": dict(preview_mem),
                "preview_miss": sorted(preview_miss),
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
        self._preview_miss = set()
        self._card_views = {}
        self._card_by_path = {}
        self._fi_by_path = {}
        self._order_paths = []
        self._path_to_index = {}
        self._selected_paths = set()
        self._anchor_path = None
        self._folder_scope = []
        self._folder_scope_label = u""
        self._scope_is_recent = False
        self._active_search_query = u""
        self._search_suppress = False
        self._search_timer = None
        self._host_filter_keys = set()
        self._category_filter_keys = set()
        self._placement_filter_keys = set()
        self._version_filter_keys = set()
        self._work_plane_filter_keys = set()  # Work Plane-Based (XAML: ImportedFilterList)
        self._shared_nested_filter_keys = set()  # reserved (quality block panel host)
        self._quality_flags = {
            "shared_only": False,
            "no_imported_cad": False,
            "limit_types": False,
            "limit_ref_planes": False,
            "limit_dimensions": False,
            "limit_nested": False,
            "limit_params": False,
            "limit_formulas": False,
            "limit_materials": False,
            "not_huge": False,
        }
        self._quality_limits = {
            "limit_types": 10,
            "limit_ref_planes": 10,
            "limit_dimensions": 10,
            "limit_nested": 10,
            "limit_params": 10,
            "limit_formulas": 5,
            "limit_materials": 10,
            "not_huge": 5.0,
        }
        self._load_filter_state_from_cfg()
        self._filter_suppress = False
        self._grid_relayout_gen = 0
        self._grid_relayout_timer = None
        # Extract preview from .rfa when thumb cache is empty (visible items only in virtual mode).
        self._browse_disk_only = False
        self._card_build_gen = 0
        self._initial_load_started = False
        self._pending_symbol_id = None
        self._pending_family_name = u""
        self._pending_family_path = None
        self._placement_status_msg = None
        self._reopen_ui_state = None
        self._suppress_tree_events = False
        self._dark_theme = config.load().get("ui_theme", "light") == "dark"
        self._virtual_mode = False
        self._virtual_scroll_gen = 0
        self._virtual_updating = False
        self._last_scroll_width = -1.0
        self._catalog_changing = False
        self._project_family_index = None
        self._project_family_index_doc = None
        self._last_escape_press_at = 0.0
        self._window_gen = 0
        self._scan_gen = 0

    def _init_window(self):
        self._search_timer = None
        self._grid_relayout_timer = None
        self._grid_relayout_gen = 0
        self._last_escape_press_at = 0.0
        self._window_gen += 1
        self.win = ui_utils.load_xaml(_THIS_DIR)
        self.ui = ui_utils.NamedUiControls(self.win, _UI_CONTROL_NAMES)
        self._status_controller = family_browser_status.StatusController(self.ui)
        self._library_controller = family_browser_library.LibraryController(self)
        self._card_brushes = ui_theme.card_brushes(
            ui_theme.DARK if self._dark_theme else ui_theme.LIGHT)
        self._props_controller = family_browser_props.PropsPanelController(
            self, self._card_brushes,
            rebuild_filters_callback=self._rebuild_meta_filters)
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

    def _apply_ui_theme(self, dark, persist=True):
        palette = ui_theme.DARK if dark else ui_theme.LIGHT
        self._dark_theme = dark
        ui_theme.apply_window_theme(self.win, palette)
        _sync_card_colors(palette)
        self._card_brushes = ui_theme.card_brushes(palette)
        if getattr(self, "_props_controller", None) is not None:
            self._props_controller.brushes = self._card_brushes
        self._refresh_cards_theme()
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
        self._update_filters_button_caption()
        btn_reset_f = getattr(self.ui, "BtnResetFilters", None)
        if btn_reset_f is not None:
            btn_reset_f.Content = i18n.t("btn_reset_filters")
        btn_apply = getattr(self.ui, "BtnApplyFilters", None)
        if btn_apply is not None:
            btn_apply.Content = i18n.t("btn_apply_filters")
        btn_run = getattr(self.ui, "BtnRunSearch", None)
        if btn_run is not None:
            btn_run.Content = i18n.t("btn_run_search")
        btn_reset = getattr(self.ui, "BtnResetSearch", None)
        if btn_reset is not None:
            btn_reset.Content = i18n.t("btn_reset_search")
        lbl_cat = getattr(self.ui, "LblCategoryFilter", None)
        if lbl_cat is not None:
            lbl_cat.Text = i18n.t("filter_category_label")
        lbl_host = getattr(self.ui, "LblHostFilter", None)
        if lbl_host is not None:
            lbl_host.Text = i18n.t("filter_host_label")
        lbl_pl = getattr(self.ui, "LblPlacementFilter", None)
        if lbl_pl is not None:
            lbl_pl.Text = i18n.t("filter_placement_label")
        lbl_ver = getattr(self.ui, "LblVersionFilter", None)
        if lbl_ver is not None:
            lbl_ver.Text = i18n.t("filter_version_label")
        lbl_imp = getattr(self.ui, "LblImportedFilter", None)
        if lbl_imp is not None:
            lbl_imp.Text = i18n.t("filter_work_plane_label")
        lbl_sn = getattr(self.ui, "LblSharedNestedFilter", None)
        if lbl_sn is not None:
            lbl_sn.Text = i18n.t("filter_quality_flags_label")
            lbl_sn.Visibility = Visibility.Visible
        sn_list = getattr(self.ui, "SharedNestedFilterList", None)
        if sn_list is not None and getattr(sn_list, "Parent", None) is not None:
            sn_list.Parent.Visibility = Visibility.Visible
        lbl_sf = getattr(self.ui, "LblSharedFamilyFilter", None)
        if lbl_sf is not None:
            lbl_sf.Visibility = Visibility.Collapsed
        sf_list = getattr(self.ui, "SharedFamilyFilterList", None)
        if sf_list is not None and getattr(sf_list, "Parent", None) is not None:
            sf_list.Parent.Visibility = Visibility.Collapsed
        self._rebuild_meta_filters(preserve=True)
        props_title = getattr(self.ui, "PropsTitle", None)
        if props_title is not None:
            props_title.Text = i18n.t("props_title")
        self._props_controller.reset()
        self._refresh_recent_header()
        self.ui.BtnSettings.Content = i18n.t("btn_library")
        self.ui.BtnSettings.ToolTip = i18n.t("btn_library_tooltip")
        self.ui.BtnReload.Content = i18n.t("btn_reload")
        self.ui.BtnReload.ToolTip = i18n.t("btn_reload_tooltip")
        self.ui.BtnLoadSelected.Content = i18n.t("btn_load")
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
            self._set_status(i18n.t("previews_done", n=n))

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
            return
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
        self._rebuild_meta_filters(preserve=True)
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
        _save_sticky_session(key, self._preview_mem, self._preview_miss)
        if async_save:
            scan = self._scan
            t = threading.Thread(
                target=self._persist_cache_worker, args=(key, scan))
            t.setDaemon(True)
            t.start()
            return
        self._persist_cache_worker(key, self._scan)

    def _persist_cache_worker(self, key, scan):
        try:
            saved, msg = libcache.save(
                key, scan, None)
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
        if self._initial_load_started:
            return
        self._initial_load_started = True
        paths = self._library_paths()
        key = libcache.cache_key(paths)
        win = self.win
        gen = self._window_gen
        libcache._log(u"startup paths={} key={}".format(paths, key))

        def worker():
            scan, disk_miss, err = None, set(), u"no_key"
            try:
                if key and libcache.cache_available(key):
                    if self.win is not win or gen != self._window_gen:
                        return
                    win.Dispatcher.Invoke(
                        System.Action(
                            lambda: self._set_status(
                                i18n.t("loading_cache"))))
                    scan, disk_miss, err = libcache.load(key)
                    if scan is None:
                        err = err or u"load_failed"
                elif key:
                    err = u"no_cache_file"
            except Exception as ex:
                err = unicode(ex)
                libcache._log(u"startup worker error: {}".format(err))
            if self.win is not win or gen != self._window_gen:
                return
            win.Dispatcher.Invoke(
                System.Action(
                    lambda: self._on_initial_load_done(scan, disk_miss, err)))

        t = threading.Thread(target=worker)
        t.setDaemon(True)
        t.start()

    def _on_initial_load_done(self, scan, disk_miss, err):
        if scan is not None:
            libcache._log(u"startup using cache (not scanning folders)")
            self._apply_cache(scan, disk_miss)
            return
        libcache._log(u"startup full scan: {} paths={}".format(
            err, self._library_paths()))
        self._build_tree({"roots": [], "all": [], "index": {}})
        self._show_recents_default()
        if self._library_path():
            self._set_status(i18n.t("scanning"))
            self._schedule_scan()
            return
        self._set_status(i18n.t("cache_not_found"))

    def _apply_cache(self, scan, disk_miss):
        self._set_status(i18n.t("building_tree"))
        self.cfg = config.load()
        sticky_key, sticky_mem, sticky_miss = _load_sticky_session()
        self._scan = self._normalize_scan(scan)
        sk = libcache.cache_key(list(sticky_key)) if sticky_key else None
        if sk == self._cache_key() and sticky_mem:
            self._preview_mem = dict(sticky_mem)
        else:
            self._preview_mem = {}
        # Never restore preview_miss (old disk-only sessions blocked all thumbnails).
        self._preview_miss = set()

        total = len(self._scan.get("all", []))
        self._build_tree(self._scan)
        self._show_recents_default()
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
        self._window_gen += 1
        # Placement closes the window and reopens it; async cache save must not
        # overwrite recent_families written right after placement.
        if self._pending_symbol_id:
            return
        ui_notify.unregister_language_listener(self._on_external_language_changed)
        ui_notify.unregister_theme_listener(self._on_external_theme_changed)
        self._persist_cache(async_save=True)

    def _on_window_preview_keydown(self, sender, e):
        try:
            if e.IsRepeat:
                return
        except Exception:
            pass

        if e.Key != Key.Escape:
            self._last_escape_press_at = 0.0
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
        u.CategoryTree.SelectedItemChanged += self._on_cat_selected
        u.FamilyScrollViewer.ScrollChanged += self._on_family_scroll
        u.FamilyScrollViewer.SizeChanged   += self._on_family_panel_resize
        u.BtnSettings.Click                += self._library_controller.on_settings
        u.BtnReload.Click                  += self._library_controller.on_reload
        u.BtnLoadSelected.Click            += lambda s, e: self._load_selected()
        btn_apply = getattr(u, "BtnApplyFilters", None)
        if btn_apply is not None:
            btn_apply.Click += self._on_apply_filters
        btn_reset_f = getattr(u, "BtnResetFilters", None)
        if btn_reset_f is not None:
            btn_reset_f.Click += self._on_reset_filters
        btn_run = getattr(u, "BtnRunSearch", None)
        if btn_run is not None:
            btn_run.Click += self._on_run_search
        btn_reset = getattr(u, "BtnResetSearch", None)
        if btn_reset is not None:
            btn_reset.Click += self._on_reset_search
        self._rebuild_meta_filters(preserve=False)
        self._update_filters_button_caption()
        self._props_controller.reset()

    def _checked_keys_from_panel(self, panel):
        keys = []
        if panel is None:
            return keys
        try:
            for child in panel.Children:
                try:
                    if not isinstance(child, CheckBox):
                        continue
                    if child.IsChecked:
                        tag = getattr(child, "Tag", None)
                        if tag is not None:
                            keys.append(as_unicode(tag))
                except Exception:
                    continue
        except Exception:
            pass
        return keys

    def _fill_check_list(self, panel, entries, selected_keys):
        """entries: list of (key, label). selected_keys: set/list of keys."""
        if panel is None:
            return
        selected = set()
        for k in selected_keys or []:
            selected.add(as_unicode(k).lower())
        panel.Children.Clear()
        for key, label in entries:
            cb = CheckBox()
            cb.Content = label
            cb.Tag = key
            cb.Margin = Thickness(0, 1, 0, 1)
            cb.Foreground = COL_TEXT
            try:
                cb.IsChecked = as_unicode(key).lower() in selected
            except Exception:
                cb.IsChecked = False
            panel.Children.Add(cb)


    def _load_filter_state_from_cfg(self):
        state = (self.cfg or {}).get("family_browser_filters") or {}

        def _setset(name, key):
            vals = state.get(key) or []
            try:
                setattr(self, name, set([as_unicode(v) for v in vals if as_unicode(v)]))
            except Exception:
                setattr(self, name, set())

        _setset("_category_filter_keys", "category")
        _setset("_host_filter_keys", "hosting")
        _setset("_placement_filter_keys", "placement")
        _setset("_version_filter_keys", "revit_format")
        _setset("_work_plane_filter_keys", "work_plane_based")

        flags = state.get("quality_flags") or {}
        for k in list(self._quality_flags.keys()):
            self._quality_flags[k] = bool(flags.get(k, self._quality_flags[k]))
        # migrate legacy multi-select Shared axis -> quality shared_only
        try:
            legacy_shared = state.get("is_shared_family") or []
            if legacy_shared and not self._quality_flags.get("shared_only"):
                vals = set(as_unicode(v).strip().lower() for v in legacy_shared if as_unicode(v).strip())
                if vals and vals.issubset(set([u"yes", u"true", u"1"])):
                    self._quality_flags["shared_only"] = True
        except Exception:
            pass

        limits = state.get("quality_limits") or {}
        for k in list(self._quality_limits.keys()):
            self._quality_limits[k] = self._coerce_quality_limit(
                k, limits.get(k, self._quality_limits[k]))

    def _save_filter_state_to_cfg(self):
        payload = {
            "category": sorted(self._category_filter_keys),
            "hosting": sorted(self._host_filter_keys),
            "placement": sorted(self._placement_filter_keys),
            "revit_format": sorted(self._version_filter_keys),
            "work_plane_based": sorted(self._work_plane_filter_keys),
            "quality_flags": dict(self._quality_flags),
            "quality_limits": dict(self._quality_limits),
        }
        self.cfg["family_browser_filters"] = payload
        try:
            config.set_value("family_browser_filters", payload)
        except Exception:
            pass

    def _coerce_quality_limit(self, key, value):
        try:
            if key == "not_huge":
                v = float(value)
                return 5.0 if v <= 0 else round(v, 3)
            v = int(value)
            return 10 if v < 1 else v
        except Exception:
            return 5.0 if key == "not_huge" else 10


    def _fill_quality_flags(self, panel):
        if panel is None:
            return
        panel.Children.Clear()
        defs = [
            ("shared_only", i18n.t("qf_shared_only"), None),
            ("no_imported_cad", i18n.t("qf_no_imported_cad"), None),
            ("limit_types", i18n.t("qf_limit_types"), "limit_types"),
            ("limit_ref_planes", i18n.t("qf_limit_ref_planes"), "limit_ref_planes"),
            ("limit_dimensions", i18n.t("qf_limit_dimensions"), "limit_dimensions"),
            ("limit_nested", i18n.t("qf_limit_nested"), "limit_nested"),
            ("limit_params", i18n.t("qf_limit_params"), "limit_params"),
            ("limit_formulas", i18n.t("qf_limit_formulas"), "limit_formulas"),
            ("limit_materials", i18n.t("qf_limit_materials"), "limit_materials"),
            ("not_huge", i18n.t("qf_not_huge"), "not_huge"),
        ]
        for key, label, limit_key in defs:
            row = StackPanel()
            row.Orientation = Orientation.Horizontal
            row.Margin = Thickness(0, 1, 0, 1)

            cb = CheckBox()
            cb.Tag = key
            cb.Content = label
            cb.Foreground = COL_TEXT
            cb.VerticalAlignment = VerticalAlignment.Center
            cb.IsChecked = bool(self._quality_flags.get(key, False))
            row.Children.Add(cb)


            panel.Children.Add(row)

    def _read_quality_flags(self, panel):
        if panel is None:
            return
        for key in list(self._quality_flags.keys()):
            self._quality_flags[key] = False

        def _read_row(row):
            cb = None
            try:
                for child in row.Children:
                    if isinstance(child, CheckBox):
                        cb = child
            except Exception:
                return
            if cb is None:
                return
            tag = as_unicode(getattr(cb, 'Tag', u''))
            if tag in self._quality_flags:
                self._quality_flags[tag] = bool(cb.IsChecked)

        try:
            for child in panel.Children:
                if isinstance(child, StackPanel):
                    _read_row(child)
                elif isinstance(child, CheckBox):
                    tag = as_unicode(getattr(child, 'Tag', u''))
                    if tag in self._quality_flags:
                        self._quality_flags[tag] = bool(child.IsChecked)
        except Exception:
            pass

    def _meta_int(self, meta, key):
        """Legacy helper: usable meta int, else 0. Prefer family_browser_quality for filters."""
        if not family_browser_quality.is_meta_usable(meta):
            return 0
        try:
            return int(meta.get(key) or 0)
        except Exception:
            return 0

    def _passes_quality_flags(self, fi):
        """AND quality flags; STRICT unknown when inspect cache missing (ADR 0003)."""
        path = getattr(fi, 'path', None) or u''
        meta = None
        try:
            if path:
                meta = family_inspector.load_cached(path)
        except Exception:
            meta = None
        return family_browser_quality.passes_quality_flags(
            fi,
            meta,
            self._quality_flags,
            limits=self._quality_limits,
        )

    def _apply_quality_flag_filters(self, families):
        if not any(self._quality_flags.values()):
            return families
        out = []
        for fi in families:
            if self._passes_quality_flags(fi):
                out.append(fi)
        return out

    def _sync_filters_from_ui(self):
        """Read filter UI into applied sets/flags (checkbox lists + quality block)."""
        def _many(panel_name):
            panel = getattr(self.ui, panel_name, None)
            return set(self._checked_keys_from_panel(panel))

        self._category_filter_keys = _many("CategoryFilterList")
        self._host_filter_keys = _many("HostFilterList")
        self._placement_filter_keys = _many("PlacementFilterList")
        self._version_filter_keys = _many("VersionFilterList")
        self._work_plane_filter_keys = _many("ImportedFilterList")  # XAML name legacy; axis = Work Plane-Based
        self._shared_nested_filter_keys = set()
        self._read_quality_flags(getattr(self.ui, "SharedNestedFilterList", None))

    def _host_label(self, key):
        mapping = {
            family_inspector.HOST_CEILING: "host_ceiling",
            family_inspector.HOST_WALL: "host_wall",
            family_inspector.HOST_FLOOR: "host_floor",
            family_inspector.HOST_ROOF: "host_roof",
            family_inspector.HOST_FACE: "host_face",
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

    def _filters_active(self):
        return bool(
            self._category_filter_keys
            or self._host_filter_keys
            or self._placement_filter_keys
            or self._version_filter_keys
            or self._work_plane_filter_keys
            or any(self._quality_flags.values())
        )

    def _rebuild_meta_filters(self, preserve=True):
        """Rebuild filter controls: checkbox lists + quality constraints."""
        if self.ui is None:
            return

        opts = family_inspector.collect_filter_options(self._folder_scope or [])
        cat_available = [as_unicode(c) for c in (opts.get("categories") or []) if as_unicode(c).strip()]

        host_keys = [
            family_inspector.HOST_CEILING,
            family_inspector.HOST_WALL,
            family_inspector.HOST_FLOOR,
            family_inspector.HOST_ROOF,
            family_inspector.HOST_FACE,
            family_inspector.HOST_INDEPENDENT,
            family_inspector.HOST_UNKNOWN,
            family_inspector.HOST_OTHER,
        ]
        for h in opts.get("hostings") or []:
            hu = as_unicode(h)
            if hu.lower() not in set(x.lower() for x in host_keys):
                host_keys.append(hu)

        place_keys = list(family_inspector.PLACEMENT_KEYS)
        for p in opts.get("placements") or []:
            pu = as_unicode(p)
            if pu.lower() not in set(x.lower() for x in place_keys):
                place_keys.append(pu)

        ver_available = [as_unicode(v) for v in (opts.get("revit_formats") or []) if as_unicode(v).strip()]
        wp_available = [as_unicode(k) for k in (opts.get("work_plane_based") or [])]

        def _pick_set(existing, available):
            if not preserve:
                return set()
            avail_l = set(as_unicode(a).lower() for a in (available or []))
            out = set()
            for k in existing or []:
                ku = as_unicode(k)
                if ku.lower() in avail_l:
                    out.add(ku)
            return out

        self._category_filter_keys = _pick_set(self._category_filter_keys, cat_available)
        self._host_filter_keys = _pick_set(self._host_filter_keys, host_keys)
        self._placement_filter_keys = _pick_set(self._placement_filter_keys, place_keys)
        self._version_filter_keys = _pick_set(self._version_filter_keys, ver_available)
        self._work_plane_filter_keys = _pick_set(self._work_plane_filter_keys, wp_available)
        self._shared_nested_filter_keys = set()

        def _bool_label(k):
            kl = as_unicode(k).strip().lower()
            if kl == u"yes":
                return i18n.t("props_yes")
            if kl == u"no":
                return i18n.t("props_no")
            return i18n.t("props_unknown")

        cat_entries = [(c, c) for c in sorted(cat_available, key=lambda s: s.lower())]
        host_entries = [(h, self._host_label(h)) for h in host_keys]
        place_entries = [(p, self._placement_label(p)) for p in place_keys]
        ver_entries = [(v, v) for v in sorted(ver_available, key=lambda s: s.lower())]
        wp_entries = [(k, _bool_label(k)) for k in sorted(set(wp_available), key=lambda s: s.lower())]

        self._filter_suppress = True
        try:
            self._fill_check_list(getattr(self.ui, "CategoryFilterList", None), cat_entries, self._category_filter_keys)
            self._fill_check_list(getattr(self.ui, "HostFilterList", None), host_entries, self._host_filter_keys)
            self._fill_check_list(getattr(self.ui, "PlacementFilterList", None), place_entries, self._placement_filter_keys)
            self._fill_check_list(getattr(self.ui, "VersionFilterList", None), ver_entries, self._version_filter_keys)
            self._fill_check_list(getattr(self.ui, "ImportedFilterList", None), wp_entries, self._work_plane_filter_keys)
            self._fill_quality_flags(getattr(self.ui, "SharedNestedFilterList", None))
        finally:
            self._filter_suppress = False
        self._update_filters_button_caption()

    def _active_filter_count(self):
        return (
            len(self._category_filter_keys)
            + len(self._host_filter_keys)
            + len(self._placement_filter_keys)
            + len(self._version_filter_keys)
            + len(self._work_plane_filter_keys)
            + sum(1 for v in self._quality_flags.values() if v)
        )

    def _update_filters_button_caption(self):
        """Show applied filter count next to the Filtering title."""
        tb = getattr(self.ui, "FiltersCount", None) if self.ui else None
        if tb is None:
            return
        n = self._active_filter_count()
        if n > 0:
            tb.Text = u"({})".format(n)
            tb.Visibility = Visibility.Visible
        else:
            tb.Text = u""
            tb.Visibility = Visibility.Collapsed

    def _close_filters_popup(self):
        return

    def _on_apply_filters(self, sender, e):
        self._sync_filters_from_ui()
        self._save_filter_state_to_cfg()
        self._update_filters_button_caption()
        query = u""
        try:
            query = as_unicode(self.ui.SearchBox.Text)
        except Exception:
            query = u""
        self._apply_search(query)

    def _on_reset_filters(self, sender, e):
        self._category_filter_keys = set()
        self._host_filter_keys = set()
        self._placement_filter_keys = set()
        self._version_filter_keys = set()
        self._work_plane_filter_keys = set()
        self._shared_nested_filter_keys = set()
        for k in list(self._quality_flags.keys()):
            self._quality_flags[k] = False
        for k in list(self._quality_limits.keys()):
            self._quality_limits[k] = self._coerce_quality_limit(k, 5.0 if k == "not_huge" else (5 if k == "limit_formulas" else 10))
        self._save_filter_state_to_cfg()
        self._rebuild_meta_filters(preserve=False)
        self._update_filters_button_caption()
        query = u""
        try:
            query = as_unicode(self.ui.SearchBox.Text)
        except Exception:
            query = u""
        self._apply_search(query)

    def _on_run_search(self, sender, e):
        self._sync_filters_from_ui()
        self._save_filter_state_to_cfg()
        self._update_filters_button_caption()
        query = u""
        try:
            query = as_unicode(self.ui.SearchBox.Text)
        except Exception:
            query = u""
        self._apply_search(query)

    def _on_reset_search(self, sender, e):
        self._stop_search_timer()
        self._active_search_query = u""
        self._category_filter_keys = set()
        self._host_filter_keys = set()
        self._placement_filter_keys = set()
        self._version_filter_keys = set()
        self._work_plane_filter_keys = set()
        self._shared_nested_filter_keys = set()
        for k in list(self._quality_flags.keys()):
            self._quality_flags[k] = False
        for k in list(self._quality_limits.keys()):
            self._quality_limits[k] = self._coerce_quality_limit(k, 5.0 if k == "not_huge" else (5 if k == "limit_formulas" else 10))
        self._save_filter_state_to_cfg()
        self._search_suppress = True
        try:
            self.ui.SearchBox.Text = u""
        finally:
            self._search_suppress = False
        self._rebuild_meta_filters(preserve=False)
        self._update_filters_button_caption()
        self._refresh_catalog_view()

    def _on_search_box_keydown(self, sender, e):
        try:
            if e.Key == Key.Enter:
                e.Handled = True
                self._on_run_search(sender, e)
        except Exception:
            pass

    def _refresh_catalog_view(self):
        """Re-apply search + meta filters to current folder scope."""
        query = as_unicode(self._active_search_query).strip()
        families = list(self._folder_scope or [])
        if query:
            families = scanner.flat_search(families, query)
        families = family_inspector.filter_families(
            families,
            category=self._category_filter_keys,
            hosting=self._host_filter_keys,
            placement=self._placement_filter_keys,
            revit_format=self._version_filter_keys,
            work_plane_based=self._work_plane_filter_keys,
        )
        families = self._apply_quality_flag_filters(families)
        self._show_families(families)
        self._update_breadcrumb_display()
        total = len(self._folder_scope or [])
        shown = len(families)
        if (query or self._filters_active()) and total != shown:
            self._update_count_display(shown, total)
        else:
            self._update_count_display(shown)
        self._props_controller.reset()
        if self._filters_active() and shown == 0 and total > 0:
            self._set_status(i18n.t("host_filter_empty"))

    def _schedule_scan(self):
        paths = self._library_paths()
        valid = [p for p in paths if os.path.isdir(p)]
        if not valid:
            self._set_status(i18n.t("library_path_required"))
            return
        paths = valid
        self._scan_gen += 1
        self._set_status(i18n.t("scanning"))
        t = threading.Thread(
            target=self._do_scan,
            args=(list(paths), self._scan_gen, self.win, self._window_gen))
        t.setDaemon(True)
        t.start()

    def _do_scan(self, paths, scan_gen, win, window_gen):
        try:
            def progress(n):
                if self.win is not win or window_gen != self._window_gen:
                    return
                if scan_gen != self._scan_gen:
                    return
                win.Dispatcher.BeginInvoke(
                    System.Action(
                        lambda c=n: self._set_status(
                            i18n.t("scanning_progress", n=c))))

            scan = scanner.scan_library(paths, progress_cb=progress)
        except Exception as ex:
            msg = i18n.t("scan_error", err=ex)
            if self.win is not win or window_gen != self._window_gen:
                return
            if scan_gen != self._scan_gen:
                return
            win.Dispatcher.Invoke(
                System.Action(lambda: self._set_status(msg)))
            return
        if self.win is not win or window_gen != self._window_gen:
            return
        if scan_gen != self._scan_gen:
            return
        win.Dispatcher.Invoke(
            System.Action(lambda: self._scan_done(scan, scan_gen)))

    def _scan_done(self, scan, scan_gen=None):
        if scan_gen is not None and scan_gen != self._scan_gen:
            return
        self._scan = self._normalize_scan(scan)
        total = len(self._scan.get("all", []))
        n_folders = len(self._scan.get("index", {}))
        key = self._cache_key()
        self._preview_miss = set()
        saved, save_msg = libcache.save(
            key, self._scan, None)
        self._invalidate_project_family_index()
        self.cfg = config.load()
        if saved:
            config.patch_fields({
                "library_cache_hash": libcache.key_hash(key),
                "library_cache_count": total,
            })
            self.cfg = config.load()
        _save_sticky_session(key, self._preview_mem, self._preview_miss)
        if saved:
            self._set_status(
                i18n.t("loaded_saved", n=total, f=n_folders))
        else:
            self._set_status(i18n.t("loaded_no_cache", n=total))
            MessageBox.Show(
                i18n.t("cache_save_failed", msg=save_msg),
                config.APP_NAME,
                MessageBoxButton.OK,
                MessageBoxImage.Warning)
        self._build_tree(self._scan)
        self._show_recents_default()

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
        recent_item.FontWeight = FontWeights.SemiBold
        tree.Items.Add(recent_item)

        for root in scan.get("roots", []):
            self._add_folder_node(tree.Items, root, is_root=True)

    def _add_folder_node(self, parent_items, node, is_root=False):
        item = TreeViewItem()
        count = node.count()
        if is_root:
            header = u"{} ({})".format(node.name, count)
            item.IsExpanded = True
        else:
            header = u"{} ({})".format(node.name, count)
        item.Header = header
        item.Tag = _TAG_FOLDER_PREFIX + node.path
        parent_items.Add(item)

        for name in sorted(node.children.keys(), key=lambda s: s.lower()):
            self._add_folder_node(item.Items, node.children[name])

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
        self._rebuild_meta_filters(preserve=True)
        self._refresh_catalog_view()

    def _on_cat_selected(self, sender, e):
        if self._suppress_tree_events:
            return
        item = self.ui.CategoryTree.SelectedItem
        if item is None:
            return
        tag = item.Tag
        if tag == "__recent__":
            self._open_catalog(
                self._recent_families(), i18n.t("recent"), is_recent=True)
        elif isinstance(tag, str) and tag.startswith(_TAG_FOLDER_PREFIX):
            folder_path = os.path.normpath(tag[len(_TAG_FOLDER_PREFIX):])
            node = self._scan.get("index", {}).get(folder_path)
            if node:
                self._show_folder(node)
            else:
                self._open_catalog([], folder_path, is_recent=False)

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

    def _all_families(self):
        return list(self._scan.get("all", []))

    def _viewport_width(self):
        sv = self.ui.FamilyScrollViewer
        w = sv.ViewportWidth if sv.ViewportWidth > 0 else sv.ActualWidth
        if w < 80 and self.win is not None:
            w = max(400.0, float(self.win.ActualWidth) - 620.0)
        if w < 80:
            w = 800.0
        return float(w)

    def _layout_metrics(self):
        """Adaptive grid: stretch cards so columns fill the viewport width."""
        w = self._viewport_width()
        gap = float(_CARD_MARGIN)
        min_w = float(_CARD_MIN_W)
        max_w = float(_CARD_MAX_W)
        cols = max(1, int((w + gap) / (min_w + gap)))
        card_w = (w - gap * (cols - 1)) / float(cols) if cols > 1 else w
        # Prefer more columns over oversized cards on wide screens.
        while card_w > max_w + 0.5:
            next_cols = cols + 1
            next_w = (w - gap * (next_cols - 1)) / float(next_cols)
            if next_w < min_w:
                break
            cols = next_cols
            card_w = next_w
        if card_w < min_w:
            cols = max(1, int((w + gap) / (min_w + gap)))
            card_w = (w - gap * (cols - 1)) / float(cols) if cols > 1 else w
        card_h = card_w * (float(_CARD_H) / float(_CARD_W))
        return cols, float(card_w), float(card_h), gap, w

    def _layout_cols(self):
        return self._layout_metrics()[0]

    def _card_slot_xy(self, index):
        cols, card_w, card_h, gap, _w = self._layout_metrics()
        col = index % cols
        row = index // cols
        x = col * (card_w + gap)
        y = row * (card_h + gap)
        return float(x), float(y)

    def _canvas_height_for(self, count):
        if count <= 0:
            return 0.0
        cols, _cw, card_h, gap, _w = self._layout_metrics()
        rows = (count + cols - 1) // cols
        return float(rows * (card_h + gap))

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

        def run():
            if gen != self._grid_relayout_gen:
                return
            self._relayout_family_grid()

        self.win.Dispatcher.BeginInvoke(System.Action(run))

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
                cols, _cw, card_h, gap, vw = self._layout_metrics()
                rows = (n + cols - 1) // cols if n else 0
                panel.Width = vw
                panel.Height = float(rows * (card_h + gap))
            self._virtual_sync_viewport()
            return

        for i, fi in enumerate(self._active):
            self._add_family_card(fi, index=i)
        if isinstance(panel, Canvas):
            _cols, _cw, _ch, _gap, vw = self._layout_metrics()
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

        def run():
            if gen != self._virtual_scroll_gen:
                return
            self._virtual_sync_viewport()

        self.win.Dispatcher.BeginInvoke(System.Action(run))

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
        return panel

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

        def done():
            if self.ui is None:
                return
            self._force_scroll_top()
            self._catalog_changing = False
            if run_virtual:
                self._virtual_sync_viewport()

        from System.Windows.Threading import DispatcherPriority
        self.win.Dispatcher.BeginInvoke(
            System.Action(done), DispatcherPriority.Loaded)

    def _virtual_sync_viewport(self):
        if not self._virtual_mode or not self._active:
            return
        families = self._active
        n = len(families)
        if n == 0:
            return

        sv = self.ui.FamilyScrollViewer
        panel = self.ui.FamilyPanel

        cols, card_w, card_h, gap, vw = self._layout_metrics()
        row_h = float(card_h + gap)
        total_rows = (n + cols - 1) // cols
        canvas_h = total_rows * row_h
        self._virtual_updating = True
        try:
            panel.Width = vw
            panel.Height = canvas_h
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

        first_row = max(0, int(scroll_y / row_h) - _VIRTUAL_ROW_BUFFER)
        last_row = min(
            total_rows,
            int((scroll_y + view_h) / row_h) + _VIRTUAL_ROW_BUFFER + 1)
        first_i = first_row * cols
        last_i = min(n, last_row * cols)
        if first_i >= last_i:
            first_i = 0
            last_i = min(n, cols * (last_row - first_row + 1))
            if last_i <= 0:
                last_i = min(n, cols)

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
        self._set_status(i18n.t("families_count", n=n))

    def _add_family_card(self, fi, index=None):
        panel = self.ui.FamilyPanel
        if fi.path in self._preview_mem:
            fi.preview = self._preview_mem[fi.path]
        _cols, card_w, card_h, _gap, _vw = self._layout_metrics()
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
        self.ui.BtnLoadSelected.IsEnabled = False
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

    def _add_card_batch(self):
        if self._card_batch_gen != self._card_build_gen:
            return
        families = self._card_batch_families
        total = len(families)
        start = self._card_batch_index
        end = min(start + _CARD_UI_BATCH, total)
        for i in range(start, end):
            self._add_family_card(families[i], index=i)
        self._card_batch_index = end
        panel = self.ui.FamilyPanel
        if isinstance(panel, Canvas):
            panel.Width = self._viewport_width()
            panel.Height = self._canvas_height_for(total)
        if end < total:
            self._set_status(
                i18n.t("loading_cards_progress", done=end, total=total))
            self.win.Dispatcher.BeginInvoke(
                System.Action(self._add_card_batch))
            return
        self._card_batch_families = None
        self._schedule_previews(
            families, disk_only=self._browse_disk_only)
        self._finish_family_view_layout()

    def _schedule_previews(self, families, disk_only=False):
        self._preview_gen += 1
        gen = self._preview_gen
        win = self.win
        window_gen = self._window_gen
        if not families:
            return
        paths = [fi.path for fi in families]
        total = len(paths)
        done = [0]
        loaded = [0]
        pending = []

        def flush_pending():
            if (not pending or gen != self._preview_gen
                    or self.win is not win
                    or window_gen != self._window_gen):
                pending[:] = []
                return
            batch = list(pending)
            pending[:] = []
            win.Dispatcher.Invoke(
                System.Action(
                    lambda items=batch: self._apply_preview_batch(items, gen)))

        def worker():
            for path in paths:
                if (gen != self._preview_gen
                        or self.win is not win
                        or window_gen != self._window_gen):
                    return
                if path in self._preview_mem or path in self._preview_miss:
                    done[0] += 1
                    continue
                png = rfa_preview.read_cached_png_bytes(path)
                if not png and not disk_only:
                    png = rfa_preview.extract_preview_png_bytes(path)
                done[0] += 1
                if not png and not disk_only:
                    self._preview_miss.add(path)
                elif gen == self._preview_gen:
                    loaded[0] += 1
                    pending.append((path, png))
                    if len(pending) >= 20:
                        flush_pending()
                if (not self._virtual_mode and done[0] % 50 == 0) or done[0] == total:
                    flush_pending()
                    if (gen == self._preview_gen and not self._virtual_mode
                            and self.win is win
                            and window_gen == self._window_gen):
                        msg = i18n.t("previews_progress",
                                       done=done[0], total=total)
                        win.Dispatcher.Invoke(
                            System.Action(lambda m=msg: self._set_status(m)))
            flush_pending()
            if (gen == self._preview_gen and not self._virtual_mode
                    and self.win is win
                    and window_gen == self._window_gen):
                msg = i18n.t("previews_done", n=total)
                win.Dispatcher.Invoke(
                    System.Action(lambda m=msg: self._set_status(m)))

        t = threading.Thread(target=worker)
        t.setDaemon(True)
        t.start()

    def _apply_preview_batch(self, items, gen):
        for path, png_bytes in items:
            self._apply_preview_png(path, png_bytes, gen)

    def _apply_preview_png(self, path, png_bytes, gen):
        if gen != self._preview_gen:
            return
        bmp = image_utils.bitmap_from_png_bytes(png_bytes)
        if bmp is None:
            return
        self._preview_mem[path] = bmp
        preview_img = self._card_views.get(path)
        if preview_img is None:
            return
        fi = self._fi_by_path.get(path)
        if fi is not None:
            fi.preview = bmp
        preview_img.Source     = bmp
        preview_img.Visibility = Visibility.Visible

    def _mods(self):
        m = Keyboard.Modifiers
        ctrl = (m & ModifierKeys.Control) == ModifierKeys.Control
        shift = (m & ModifierKeys.Shift) == ModifierKeys.Shift
        return ctrl, shift

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
            if path not in self._fi_by_path:
                continue
            self._selected_paths.add(path)
            self._set_card_selected(path, True)

    def _toggle_path(self, path):
        if path in self._selected_paths:
            self._selected_paths.discard(path)
            self._set_card_selected(path, False)
        else:
            self._selected_paths.add(path)
            self._set_card_selected(path, True)

    def _range_paths(self, anchor, target):
        if anchor not in self._order_paths or target not in self._order_paths:
            return [target]
        i0 = self._order_paths.index(anchor)
        i1 = self._order_paths.index(target)
        if i0 > i1:
            i0, i1 = i1, i0
        return self._order_paths[i0:i1 + 1]

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
        if e.ClickCount >= 2:
            self._reveal_in_explorer(fi)
            e.Handled = True

    def _on_card_click(self, card, fi, e):
        if e.ClickCount >= 2:
            self._place_family(fi)
            return
        path = fi.path
        ctrl, shift = self._mods()
        if shift and self._anchor_path:
            paths = self._range_paths(self._anchor_path, path)
            self._select_paths(paths, replace=not ctrl)
        elif ctrl:
            self._toggle_path(path)
            self._anchor_path = path
        else:
            self._select_paths([path], replace=True)
            self._anchor_path = path
        self._update_selection_status()

    def _update_selection_status(self):
        n = len(self._selected_paths)
        self.ui.BtnLoadSelected.IsEnabled = n > 0
        if n == 0:
            self._props_controller.reset()
            return
        if n == 1:
            fi = self._fi_by_path.get(list(self._selected_paths)[0])
            if fi:
                ver = as_unicode(getattr(fi, "revit_version", u"") or u"")
                folder = as_unicode(getattr(fi, "folder", u"") or u"")
                size_mb = fi.size_kb / 1024.0
                self._set_status(i18n.t(
                    "status_item",
                    folder=folder,
                    name=as_unicode(fi.name),
                    size=i18n.t("size_mb").format(size_mb),
                    ver=ver or i18n.t("ver_unknown")))
                self._props_controller.inspect(fi)
            else:
                self._props_controller.reset()
            return
        self._props_controller.reset(i18n.t("selected_count", n=n))
        self._set_status(i18n.t("selected_count", n=n))

    def _on_clear_search(self, sender, e):
        if not self.ui.SearchBox.Text.strip():
            return
        self._stop_search_timer()
        self._reset_search_field()
        self._active_search_query = u""
        self._refresh_catalog_view()

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

    def _load_selected(self):
        paths = [p for p in self._order_paths if p in self._selected_paths]
        if not paths:
            return
        if len(paths) == 1:
            fi = self._fi_by_path.get(paths[0])
            if fi:
                self._load_family(fi)
            return
        self._load_families(paths)

    def _load_family(self, fi):
        self._load_families([fi.path])

    def _find_family_in_project(self, fi):
        keys = set()
        for name in family_utils.family_name_candidates(fi):
            keys.add(family_utils.normalize_family_key(name))
        keys.discard(u"")
        if not keys:
            return None
        idx = (
            self._project_family_index
            if self._project_family_index_ready()
            else self._build_project_family_index_sync())
        for key in keys:
            fam = idx.get(key)
            if fam is not None:
                return fam
        file_key = family_utils.normalize_family_key(fi.name)
        if not file_key or len(file_key) < 4:
            return None
        best = None
        for fam_key, fam in idx.items():
            if fam_key == file_key or file_key in fam_key or fam_key in file_key:
                best = fam
        return best

    def _load_family_element(self, fi):
        """Return (Family, error_message). error_message is None on success."""
        path = os.path.normpath(fi.path)
        if not os.path.isfile(path):
            return None, i18n.t("file_not_found_short")

        err_text = None

        try:
            fam_ref = clr.Reference[RevitFamily]()
            if (self.doc.LoadFamily(path, family_load_options.FAMILY_LOAD_OPTIONS, fam_ref)
                    and fam_ref.Value is not None):
                return fam_ref.Value, None
        except Exception as ex:
            err_text = as_unicode(ex)

        fam = self._find_family_in_project(fi)
        if fam is not None:
            return fam, None

        if err_text:
            return None, err_text
        ver = as_unicode(getattr(fi, "revit_version", u"") or u"")
        hint = i18n.t("load_hint_ver", ver=ver) if ver else u""
        return None, i18n.t("load_failed", hint=hint)

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

    def _get_family_symbol(self, fi):
        """Load .rfa if needed and return a FamilySymbol ready to place."""
        t = Transaction(self.doc, i18n.t("txn_load"))
        t.Start()
        try:
            fam, err = self._load_family_element(fi)
            if fam is None:
                t.RollBack()
                raise Exception(err or u"LoadFamily failed")
            symbol = self._get_placeable_symbol(fam, fi)
            if symbol is None:
                t.RollBack()
                raise Exception(
                    i18n.t("no_symbol", name=revit_name(fam)))
            if not symbol.IsActive:
                symbol.Activate()
            t.Commit()
            self._invalidate_project_family_index()
            return symbol
        except Exception:
            try:
                t.RollBack()
            except Exception:
                pass
            raise

    def _place_family(self, fi):
        uidoc = revit.uidoc
        if uidoc is None or uidoc.ActiveView is None:
            self._set_status(i18n.t("no_active_view"))
            return
        try:
            symbol = self._get_family_symbol(fi)
        except Exception as ex:
            self._set_status(i18n.t("load_error", err=as_unicode(ex)))
            return
        if symbol is None:
            self._set_status(
                i18n.t("place_prepare_failed", name=fi.name))
            return
        search_query = u""
        if self.ui is not None:
            search_query = as_unicode(self.ui.SearchBox.Text).strip()
        self._reopen_ui_state = {
            "scope": list(self._folder_scope),
            "label": self._folder_scope_label,
            "tree_tag": self._current_tree_tag(),
            "search_query": search_query,
        }
        self._pending_symbol_id = symbol.Id.IntegerValue
        self._pending_family_name = as_unicode(fi.name)
        self._pending_family_path = libcache._norm_path(fi.path)
        config.add_recent(self._pending_family_path)
        self.cfg = config.load()
        self.win.Close()

    def _run_pending_placement(self, sym_id, family_name, family_path):
        uidoc = revit.uidoc
        if uidoc is None or uidoc.ActiveView is None or not sym_id:
            return u""
        try:
            symbol = self.doc.GetElement(ElementId(int(sym_id)))
            if symbol is None:
                return i18n.t("family_not_in_project")
            if not symbol.IsActive:
                t = Transaction(self.doc, i18n.t("txn_activate"))
                t.Start()
                try:
                    symbol.Activate()
                    t.Commit()
                except Exception:
                    try:
                        t.RollBack()
                    except Exception:
                        pass
                    raise
            try:
                uidoc.PromptForFamilyInstancePlacement(symbol)
            except OperationCanceledException:
                return i18n.t("placement_cancelled")
            return i18n.t("placed", name=family_name)
        except Exception as ex:
            return i18n.t("placement_error", err=ex)

    def _pump_ui_before_reopen(self):
        """Let Revit/WPF finish the placement command before ShowDialog again."""
        try:
            from System.Windows.Threading import (
                Dispatcher, DispatcherFrame, DispatcherPriority)
            app = System.Windows.Application.Current
            if app is not None:
                frame = DispatcherFrame()

                def stop_frame():
                    frame.Continue = False

                app.Dispatcher.BeginInvoke(
                    DispatcherPriority.ApplicationIdle,
                    System.Action(stop_frame))
                Dispatcher.PushFrame(frame)
                return
        except Exception as ex:
            libcache._log(u"pump_ui: {}".format(as_unicode(ex)))
        try:
            System.Threading.Thread.Sleep(200)
        except Exception:
            pass

    def _load_families(self, paths):
        t = None
        loaded = []
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
                    continue
                try:
                    fam, err = self._load_family_element(fi)
                    if fam is not None:
                        loaded.append(fi.name)
                        config.add_recent(fi.path)
                    elif err:
                        errors.append(u"{}: {}".format(fi.name, err))
                    else:
                        skipped.append(fi.name)
                except Exception as ex:
                    errors.append(u"{}: {}".format(fi.name, ex))
            if loaded:
                t.Commit()
                self.cfg = config.load()
            else:
                t.RollBack()
        except Exception as ex:
            if t is not None:
                try:
                    t.RollBack()
                except Exception:
                    pass
            self._set_status(i18n.t("error_generic", err=str(ex)))
            return

        parts = []
        if loaded:
            parts.append(i18n.t("loaded_n", n=len(loaded)))
        if skipped:
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
        first_open = True
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

            self.win.ShowDialog()

            pending_id = self._pending_symbol_id
            pending_name = self._pending_family_name
            pending_path = self._pending_family_path
            self._pending_symbol_id = None
            self._pending_family_name = u""
            self._pending_family_path = None
            self.win = None
            self.ui = None

            if not pending_id:
                break

            self._placement_status_msg = self._run_pending_placement(
                pending_id, pending_name, pending_path)
            self._pump_ui_before_reopen()


# ---------------------------------------------------------------------------
# pyRevit entry — runs when the button is clicked
# ---------------------------------------------------------------------------
dlg = FamilyBrowserDialog()
dlg.show()