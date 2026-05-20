# -*- coding: utf-8 -*-
"""
Диспетчер семейств — pyRevit extension (AVRO)
Entry point script.
"""
import os
import sys
import threading
import codecs
import tempfile

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
    Thickness, HorizontalAlignment, Visibility,
    MessageBox, MessageBoxButton, MessageBoxImage,
    TextWrapping, FrameworkElement,
)
from System.Windows.Controls import (
    TreeViewItem, Border, StackPanel, TextBlock, Image
)
from System.Windows.Media import SolidColorBrush, Color, VisualTreeHelper, Stretch
from System.Windows.Input import Keyboard, ModifierKeys
from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption
from System.IO import MemoryStream
from System.Windows.Markup import XamlReader
from System.Windows.Forms import FolderBrowserDialog, DialogResult
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
import rfa_preview
import rfa_version
import library_cache as libcache

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
def _as_unicode(text):
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    try:
        return unicode(text)
    except Exception:
        return u""


def _brush(r, g, b):
    c = Color.FromRgb(r, g, b)
    br = SolidColorBrush(c)
    br.Freeze()
    return br


def _revit_name(element):
    """
    Read Element.Name under IronPython.

    ``from … import Family`` breaks ``element.Name`` (NameError: Name).
    """
    if element is None:
        return u""
    try:
        return _as_unicode(
            RevitElement.Name.__get__(element, type(element)))
    except Exception:
        pass
    try:
        return _as_unicode(getattr(element, "Name"))
    except Exception:
        return u""


def _symbol_family(symbol):
    """FamilySymbol.Family — same IronPython shadowing as .Name."""
    if symbol is None:
        return None
    try:
        return getattr(symbol, "Family")
    except Exception:
        return None


class _FamilyLoadOptions(IFamilyLoadOptions):
    """Allow reload/overwrite when the family is already in the project."""

    @staticmethod
    def _set_out_bool(out_param, value):
        try:
            out_param.Value = value
        except Exception:
            try:
                out_param[0] = value
            except Exception:
                pass

    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        self._set_out_bool(overwriteParameterValues, True)
        return True

    def OnSharedFamilyFound(
            self, sharedFamily, familyInUse, source, overwriteParameterValues):
        self._set_out_bool(overwriteParameterValues, True)
        try:
            source.Value = RDB.FamilySource(0)
        except Exception:
            try:
                source[0] = RDB.FamilySource(0)
            except Exception:
                pass
        return True


_FAMILY_LOAD_OPTIONS = _FamilyLoadOptions()


def _normalize_family_key(name):
    if not name:
        return u""
    key = _as_unicode(name).lower().replace(u" ", u"")
    key = key.replace(u"__", u"_")
    return key


def _family_name_candidates(fi):
    """Possible Revit family names for a library file."""
    names = set()
    base = _as_unicode(fi.name)
    if base:
        names.add(base)
        names.add(base.replace(u"__", u"_"))
        names.add(base.replace(u"_", u" "))
    path = getattr(fi, "path", u"") or u""
    if path:
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem:
            names.add(stem)
            names.add(stem.replace(u"__", u"_"))
    try:
        from Autodesk.Revit.DB import BasicFileInfo
        bfi = BasicFileInfo.Extract(path)
        for attr in ("GetFamilyName",):
            fn = getattr(bfi, attr, None)
            if callable(fn):
                try:
                    v = _as_unicode(fn())
                    if v:
                        names.add(v)
                except Exception:
                    pass
    except Exception:
        pass
    return names


COL_CARD     = _brush(0xFF, 0xFF, 0xFF)
COL_CARD_HOV = _brush(0xE8, 0xF4, 0xFC)
COL_CARD_SEL = _brush(0xCC, 0xE8, 0xFF)
COL_TEXT     = _brush(0x1E, 0x1E, 0x1E)
COL_MUTED    = _brush(0x5A, 0x5A, 0x5A)
COL_BORDER   = _brush(0xAB, 0xAB, 0xAB)

# ---------------------------------------------------------------------------
# Load XAML
# ---------------------------------------------------------------------------
def _load_xaml():
    xaml_path = os.path.join(_THIS_DIR, "ui.xaml")
    with codecs.open(xaml_path, "r", "utf-8") as f:
        xaml_str = f.read()
    return XamlReader.Parse(xaml_str)


_UI_CONTROL_NAMES = [
    "SearchBox", "BtnClearSearch",
    "CategoryTree", "BtnSettings", "BtnReload", "BtnLoadSelected",
    "FamilyPanel", "BreadcrumbText", "CountText", "StatusText",
]


def _find_named(root, name):
    ctrl = root.FindName(name)
    if ctrl is not None:
        return ctrl
    return _find_in_visual_tree(root, name)


def _find_in_visual_tree(element, name):
    if element is None:
        return None
    if isinstance(element, FrameworkElement) and element.Name == name:
        return element
    count = VisualTreeHelper.GetChildrenCount(element)
    for i in range(count):
        child = VisualTreeHelper.GetChild(element, i)
        found = _find_in_visual_tree(child, name)
        if found is not None:
            return found
    return None


class NamedUiControls(object):
    """Resolve x:Name elements after XamlReader.Parse (no code-behind fields)."""

    def __init__(self, root):
        missing = []
        for name in _UI_CONTROL_NAMES:
            ctrl = _find_named(root, name)
            if ctrl is None:
                missing.append(name)
            else:
                setattr(self, name, ctrl)
        if missing:
            raise Exception(
                "Named controls not found in ui.xaml: " + ", ".join(missing))

_TAG_FOLDER_PREFIX = "folder:"
# Build large folder grids in UI batches so the window stays responsive.
_CARD_UI_BATCH = 50
_CARD_UI_BATCH_THRESHOLD = 100
_CARD_W = 156
_CARD_H = 182
_PREVIEW_W = 96
_PREVIEW_H = 67
_STICKY_KEY = "AVRO_session"


def _library_cache_key(paths):
    return libcache.cache_key(paths)


def clear_library_cache():
    libcache.clear()
    _save_sticky_session(None, {}, set())
    try:
        cfg = config.load()
        cfg["library_cache_hash"] = ""
        cfg["library_cache_count"] = 0
        config.save(cfg)
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


def _bitmap_from_png_bytes(image_bytes):
    """Load PNG or JPEG bytes into WPF BitmapImage (IronPython-safe via temp file)."""
    if not image_bytes:
        return None
    is_jpeg = (
        len(image_bytes) >= 2
        and image_bytes[0] == "\xff"
        and image_bytes[1] == "\xd8")
    suffix = ".jpg" if is_jpeg else ".png"
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.write(fd, image_bytes)
        os.close(fd)
        bmp = BitmapImage()
        bmp.BeginInit()
        bmp.UriSource = System.Uri(tmp_path)
        bmp.CacheOption = BitmapCacheOption.OnLoad
        bmp.EndInit()
        bmp.Freeze()
        return bmp
    except Exception:
        try:
            from System import Array, Byte
            buf = Array.CreateInstance(Byte, len(image_bytes))
            for i, ch in enumerate(image_bytes):
                buf[i] = ord(ch)
            ms = MemoryStream(buf)
            bmp = BitmapImage()
            bmp.BeginInit()
            bmp.StreamSource = ms
            bmp.CacheOption = BitmapCacheOption.OnLoad
            bmp.EndInit()
            bmp.Freeze()
            return bmp
        except Exception:
            return None
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _make_card(fi, dialog):
    """Build a WPF card for one family (grid with preview)."""
    card = Border()
    card.Background   = COL_CARD
    card.BorderBrush  = COL_BORDER
    card.BorderThickness = Thickness(1)
    card.CornerRadius = System.Windows.CornerRadius(2)
    card.Margin       = Thickness(5)
    card.Padding      = Thickness(8)
    card.Cursor       = System.Windows.Input.Cursors.Hand
    card.Width        = _CARD_W
    card.Height       = _CARD_H
    card.Tag          = fi

    sp = StackPanel()
    sp.HorizontalAlignment = HorizontalAlignment.Center

    preview_img = Image()
    preview_img.Width                = _PREVIEW_W
    preview_img.Height               = _PREVIEW_H
    preview_img.Stretch              = Stretch.Uniform
    preview_img.HorizontalAlignment  = HorizontalAlignment.Center
    preview_img.Margin               = Thickness(0, 4, 0, 6)
    preview_img.Visibility           = Visibility.Collapsed

    if fi.preview is not None:
        preview_img.Source     = fi.preview
        preview_img.Visibility = Visibility.Visible

    name_block = TextBlock()
    name_block.Text                = _as_unicode(fi.name)
    name_block.Foreground          = COL_TEXT
    name_block.FontSize            = 11
    name_block.TextWrapping        = TextWrapping.Wrap
    name_block.TextAlignment       = System.Windows.TextAlignment.Center
    name_block.MaxHeight           = 36

    size_block = TextBlock()
    size_mb = fi.size_kb / 1024.0
    size_block.Text                = u"{:.2f} МБ".format(size_mb)
    size_block.Foreground          = COL_MUTED
    size_block.FontSize            = 10
    size_block.HorizontalAlignment = HorizontalAlignment.Center
    size_block.Margin              = Thickness(0, 2, 0, 0)

    ver_label = _as_unicode(getattr(fi, "revit_version", u"") or u"")
    if not ver_label:
        ver_label = rfa_version.revit_version_label(fi.path)
        fi.revit_version = ver_label
    version_block = TextBlock()
    version_block.Text                = ver_label if ver_label else u"—"
    version_block.Foreground          = COL_MUTED
    version_block.FontSize            = 11
    version_block.FontWeight          = System.Windows.FontWeights.SemiBold
    version_block.HorizontalAlignment = HorizontalAlignment.Center
    version_block.Margin              = Thickness(0, 4, 0, 0)

    sp.Children.Add(preview_img)
    sp.Children.Add(name_block)
    sp.Children.Add(size_block)
    sp.Children.Add(version_block)
    card.Child = sp

    def mouse_enter(s, e):
        if fi.path not in dialog._selected_paths:
            s.Background = COL_CARD_HOV

    def mouse_leave(s, e):
        if fi.path not in dialog._selected_paths:
            s.Background = COL_CARD

    def mouse_click(s, e):
        dialog._on_card_click(s, fi, e)

    card.MouseEnter          += mouse_enter
    card.MouseLeave          += mouse_leave
    card.MouseLeftButtonDown += mouse_click

    return card, preview_img


# ---------------------------------------------------------------------------
# Dialog class
# ---------------------------------------------------------------------------
class FamilyManagerDialog(object):

    def __init__(self):
        self.win = None
        self.ui = None
        self.doc = revit.doc
        self.cfg = config.load()
        self._scan = {"roots": [], "all": [], "index": {}}
        self._active = []
        self._preview_gen = 0
        self._preview_mem = {}
        self._preview_miss = set()
        self._card_views = {}
        self._card_by_path = {}
        self._fi_by_path = {}
        self._order_paths = []
        self._selected_paths = set()
        self._anchor_path = None
        self._folder_scope = []
        self._folder_scope_label = u""
        self._search_suppress = False
        # True: only read thumb cache when browsing; never parse .rfa on folder click.
        self._browse_disk_only = True
        self._card_build_gen = 0
        self._initial_load_started = False
        self._pending_symbol_id = None
        self._pending_family_name = u""
        self._pending_family_path = None
        self._placement_status_msg = None
        self._reopen_ui_state = None
        self._suppress_tree_events = False

    def _init_window(self):
        self.win = _load_xaml()
        self.ui = NamedUiControls(self.win)
        self._bind()
        self.win.Closing += self._on_window_closing

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
        search_query = _as_unicode(state.get("search_query", u"")).strip()

        if tag == "__recent__":
            self._folder_scope = list(self._recent_families())
            self._folder_scope_label = u"Недавние"
        else:
            self._folder_scope = scope
            self._folder_scope_label = label

        if search_query:
            self._search_suppress = True
            try:
                self.ui.SearchBox.Text = search_query
            finally:
                self._search_suppress = False
            self._apply_search(search_query)
        else:
            self._reset_search_field()
            self._set_breadcrumb(self._folder_scope_label)
            self._show_families(list(self._folder_scope))

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
        all_families = root.descendants()
        return {
            "roots": [root],
            "all": all_families,
            "index": scanner.index_folder_tree([root]),
        }

    def _cache_key(self):
        return _library_cache_key(self._library_paths())

    def _persist_cache(self):
        key = self._cache_key()
        if not key or not self._scan.get("all"):
            return
        # Reload so we never write stale ``recent_families`` over newer disk state.
        self.cfg = config.load()
        saved, msg = libcache.save(key, self._scan, self._preview_miss)
        if saved:
            self.cfg["library_cache_hash"] = libcache.key_hash(key)
            self.cfg["library_cache_count"] = len(self._scan.get("all", []))
            config.save(self.cfg)
        else:
            libcache._log(u"persist failed: {}".format(msg))
        _save_sticky_session(key, self._preview_mem, self._preview_miss)

    def _start_initial_load(self):
        if self._initial_load_started:
            return
        self._initial_load_started = True
        paths = self._library_paths()
        key = libcache.cache_key(paths)
        libcache._log(u"startup paths={} key={}".format(paths, key))

        def worker():
            scan, disk_miss, err = None, set(), u"no_key"
            try:
                if key and libcache.cache_available(key):
                    self.win.Dispatcher.Invoke(
                        System.Action(
                            lambda: self._set_status(
                                u"Загрузка индекса из кэша\u2026")))
                    scan, disk_miss, err = libcache.load(key)
                    if scan is None:
                        err = err or u"load_failed"
                elif key:
                    err = u"no_cache_file"
            except Exception as ex:
                err = unicode(ex)
                libcache._log(u"startup worker error: {}".format(err))
            self.win.Dispatcher.Invoke(
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
        self._set_status(
            u"Кэш не найден. Нажмите «Обновить» для сканирования библиотеки.")

    def _apply_cache(self, scan, disk_miss):
        sticky_key, sticky_mem, sticky_miss = _load_sticky_session()
        self._scan = self._normalize_scan(scan)
        sk = libcache.cache_key(list(sticky_key)) if sticky_key else None
        if sk == self._cache_key() and sticky_mem:
            self._preview_mem = dict(sticky_mem)
            self._preview_miss = set(sticky_miss)
        else:
            self._preview_mem = {}
            self._preview_miss = set(disk_miss)

        total = len(self._scan.get("all", []))
        self._build_tree(self._scan)
        self._browse_disk_only = True
        self._show_recents_default()
        self._set_status(
            u"Из кэша: {} семейств. «Обновить» — пересканировать папки.".format(
                total))

    def _try_restore_cache(self):
        paths = self._library_paths()
        key = libcache.cache_key(paths)
        libcache._log(u"restore try paths={} key={}".format(paths, key))
        if not key:
            libcache._log(u"restore: no cache key")
            return False
        self._set_status(u"Loading library cache\u2026")
        scan, disk_miss, err = libcache.load(key)
        if scan is None:
            libcache._log(u"restore failed: {} key={}".format(err, key))
            return False
        self._apply_cache(scan, disk_miss)
        return True

    def _on_window_closing(self, sender, e):
        self._persist_cache()

    def _bind(self):
        u = self.ui
        u.SearchBox.TextChanged            += self._on_search
        u.BtnClearSearch.Click             += self._on_clear_search
        u.CategoryTree.SelectedItemChanged += self._on_cat_selected
        u.BtnSettings.Click                += self._on_settings
        u.BtnReload.Click                  += self._on_reload
        u.BtnLoadSelected.Click            += lambda s, e: self._load_selected()

    def _schedule_scan(self):
        paths = self._library_paths()
        valid = [p for p in paths if os.path.isdir(p)]
        if not valid:
            self._set_status(
                u"Путь к библиотеке не задан. Нажмите «Библиотека».")
            return
        paths = valid
        self._set_status(u"Сканирование библиотеки\u2026")
        t = threading.Thread(target=self._do_scan, args=(list(paths),))
        t.setDaemon(True)
        t.start()

    def _do_scan(self, paths):
        try:
            scan = scanner.scan_library(paths)
        except Exception as ex:
            msg = u"Ошибка сканирования: {}".format(ex)
            self.win.Dispatcher.Invoke(
                System.Action(lambda: self._set_status(msg)))
            return
        self.win.Dispatcher.Invoke(
            System.Action(lambda: self._scan_done(scan)))

    def _scan_done(self, scan):
        self._scan = self._normalize_scan(scan)
        total = len(self._scan.get("all", []))
        n_folders = len(self._scan.get("index", {}))
        key = self._cache_key()
        self._preview_miss = set()
        saved, save_msg = libcache.save(key, self._scan, self._preview_miss)
        self.cfg = config.load()
        if saved:
            self.cfg["library_cache_hash"] = libcache.key_hash(key)
            self.cfg["library_cache_count"] = total
            config.save(self.cfg)
        _save_sticky_session(key, self._preview_mem, self._preview_miss)
        if saved:
            self._set_status(u"Загружено: {} семейств, {} папок (кэш сохранён)".format(
                total, n_folders))
        else:
            self._set_status(
                u"Загружено: {} семейств (кэш не сохранён — см. cache.log)".format(
                    total))
            MessageBox.Show(
                u"Не удалось сохранить кэш библиотеки:\n{}\n\n"
                u"Список в памяти. Проверьте права или "
                u"%APPDATA%\\pyRevit\\AVRO\\cache.log.".format(
                    save_msg),
                config.APP_NAME,
                MessageBoxButton.OK,
                MessageBoxImage.Warning)
        self._build_tree(self._scan)
        self._show_recents_default()

    def _build_tree(self, scan):
        tree = self.ui.CategoryTree
        tree.Items.Clear()

        recent_item = TreeViewItem()
        recent_item.Header = u"Недавние"
        recent_item.Tag    = "__recent__"
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

    def _reset_search_field(self):
        self._search_suppress = True
        try:
            self.ui.SearchBox.Text = u""
        finally:
            self._search_suppress = False

    def _recent_families(self):
        """Same order as ``recent_families`` in config: last loaded first."""
        by_path = {}
        for fi in self._all_families():
            np = libcache._norm_path(fi.path)
            by_path[np] = fi
        ordered = []
        seen = set()
        for p in self.cfg.get("recent_families", []):
            np = libcache._norm_path(p)
            if np in seen:
                continue
            fi = by_path.get(np)
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
        """Default view on every open: «Недавние»."""
        self._open_catalog(self._recent_families(), u"Недавние")
        self._select_recents_tree_item()

    def _open_catalog(self, families, breadcrumb):
        """Show a folder catalog; search is limited to these families."""
        self._folder_scope = list(families)
        self._folder_scope_label = breadcrumb
        self._reset_search_field()
        self._set_breadcrumb(breadcrumb)
        self._show_families(families)

    def _on_cat_selected(self, sender, e):
        if self._suppress_tree_events:
            return
        item = self.ui.CategoryTree.SelectedItem
        if item is None:
            return
        tag = item.Tag
        if tag == "__recent__":
            self._open_catalog(self._recent_families(), u"Недавние")
        elif isinstance(tag, str) and tag.startswith(_TAG_FOLDER_PREFIX):
            folder_path = os.path.normpath(tag[len(_TAG_FOLDER_PREFIX):])
            node = self._scan.get("index", {}).get(folder_path)
            if node:
                self._show_folder(node)
            else:
                self._open_catalog([], folder_path)

    def _show_folder(self, node):
        breadcrumb = self._folder_breadcrumb(node)
        self._open_catalog(node.descendants(), breadcrumb)

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

    def _add_family_card(self, fi):
        panel = self.ui.FamilyPanel
        if fi.path in self._preview_mem:
            fi.preview = self._preview_mem[fi.path]
        card, preview_img = _make_card(fi, self)
        self._fi_by_path[fi.path] = fi
        self._card_views[fi.path] = preview_img
        self._card_by_path[fi.path] = card
        self._order_paths.append(fi.path)
        panel.Children.Add(card)

    def _show_families(self, families):
        self._active = families
        self._card_build_gen += 1
        gen = self._card_build_gen
        self._preview_gen += 1

        panel = self.ui.FamilyPanel
        panel.Children.Clear()
        self._card_views = {}
        self._card_by_path = {}
        self._fi_by_path = {}
        self._order_paths = []
        self._selected_paths = set()
        self._anchor_path = None
        self.ui.BtnLoadSelected.IsEnabled = False

        n = len(families)
        self.ui.CountText.Text = u"{} шт.".format(n)
        if not families:
            return

        if n <= _CARD_UI_BATCH_THRESHOLD:
            for fi in families:
                self._add_family_card(fi)
            self._schedule_previews(
                families, disk_only=self._browse_disk_only)
            return

        self._card_batch_families = list(families)
        self._card_batch_index = 0
        self._card_batch_gen = gen
        self._set_status(u"Загрузка: 0 / {} семейств\u2026".format(n))
        self._add_card_batch()

    def _add_card_batch(self):
        if self._card_batch_gen != self._card_build_gen:
            return
        families = self._card_batch_families
        total = len(families)
        start = self._card_batch_index
        end = min(start + _CARD_UI_BATCH, total)
        for fi in families[start:end]:
            self._add_family_card(fi)
        self._card_batch_index = end
        if end < total:
            self._set_status(
                u"Загрузка: {} / {} семейств\u2026".format(end, total))
            self.win.Dispatcher.BeginInvoke(
                System.Action(self._add_card_batch))
            return
        self._card_batch_families = None
        self._schedule_previews(
            families, disk_only=self._browse_disk_only)

    def _schedule_previews(self, families, disk_only=False):
        self._preview_gen += 1
        gen = self._preview_gen
        if not families:
            return
        paths = [fi.path for fi in families]
        total = len(paths)
        done = [0]
        loaded = [0]
        pending = []

        def flush_pending():
            if not pending or gen != self._preview_gen:
                pending[:] = []
                return
            batch = list(pending)
            pending[:] = []
            self.win.Dispatcher.Invoke(
                System.Action(
                    lambda items=batch: self._apply_preview_batch(items, gen)))

        def worker():
            for path in paths:
                if gen != self._preview_gen:
                    return
                if path in self._preview_mem or path in self._preview_miss:
                    done[0] += 1
                    continue
                png = rfa_preview.read_cached_png_bytes(path)
                if not png:
                    png = rfa_preview.extract_preview_png_bytes(path)
                done[0] += 1
                if not png:
                    self._preview_miss.add(path)
                elif gen == self._preview_gen:
                    loaded[0] += 1
                    pending.append((path, png))
                    if len(pending) >= 20:
                        flush_pending()
                if done[0] % 50 == 0 or done[0] == total:
                    flush_pending()
                    if gen == self._preview_gen:
                        msg = u"Обработано семейств: {} / {}".format(
                            done[0], total)
                        self.win.Dispatcher.Invoke(
                            System.Action(lambda m=msg: self._set_status(m)))
            flush_pending()
            if gen == self._preview_gen:
                msg = u"Готово: {} семейств.".format(total)
                self.win.Dispatcher.Invoke(
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
        bmp = _bitmap_from_png_bytes(png_bytes)
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
            card.BorderBrush = _brush(0x33, 0x99, 0xFF)
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
            return
        if n == 1:
            fi = self._fi_by_path.get(list(self._selected_paths)[0])
            if fi:
                ver = _as_unicode(getattr(fi, "revit_version", u"") or u"")
                folder = _as_unicode(getattr(fi, "folder", u"") or u"")
                size_mb = fi.size_kb / 1024.0
                self._set_status(u"{}  |  {}  |  {:.2f} МБ  |  {}".format(
                    folder, _as_unicode(fi.name), size_mb, ver or u"?"))
            return
        self._set_status(u"Выбрано семейств: {}".format(n))

    def _on_clear_search(self, sender, e):
        if not self.ui.SearchBox.Text.strip():
            return
        self._reset_search_field()
        self._show_families(self._folder_scope)
        self._set_breadcrumb(self._folder_scope_label)

    def _apply_search(self, query):
        query = _as_unicode(query).strip()
        if not query:
            self._show_families(self._folder_scope)
            self._set_breadcrumb(self._folder_scope_label)
            return
        if not self._folder_scope:
            self._show_families([])
            return
        results = scanner.flat_search(self._folder_scope, query)
        self._show_families(results)
        self._set_breadcrumb(
            u"{} / Поиск: «{}»".format(self._folder_scope_label, query))
        self.ui.CountText.Text = u"{} / {} шт.".format(
            len(results), len(self._folder_scope))

    def _on_search(self, sender, e):
        if self._search_suppress:
            return
        self._apply_search(self.ui.SearchBox.Text)

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
        for name in _family_name_candidates(fi):
            keys.add(_normalize_family_key(name))
        keys.discard(u"")
        file_key = _normalize_family_key(fi.name)
        best = None
        for fam in FilteredElementCollector(self.doc).OfClass(RevitFamily):
            fam_key = _normalize_family_key(_revit_name(fam))
            if fam_key in keys:
                return fam
            if file_key and len(file_key) >= 4:
                if fam_key == file_key or file_key in fam_key or fam_key in file_key:
                    best = fam
        return best

    def _load_family_element(self, fi):
        """Return (Family, error_message). error_message is None on success."""
        path = os.path.normpath(fi.path)
        if not os.path.isfile(path):
            return None, u"Файл не найден"

        err_text = None

        try:
            fam_ref = clr.Reference[RevitFamily]()
            if (self.doc.LoadFamily(path, _FAMILY_LOAD_OPTIONS, fam_ref)
                    and fam_ref.Value is not None):
                return fam_ref.Value, None
        except Exception as ex:
            err_text = _as_unicode(ex)

        fam = self._find_family_in_project(fi)
        if fam is not None:
            return fam, None

        if err_text:
            return None, err_text
        ver = _as_unicode(getattr(fi, "revit_version", u"") or u"")
        hint = u" (файл {})".format(ver) if ver else u""
        return None, (
            u"Не удалось загрузить семейство{}. "
            u"Проверьте версию Revit или нажмите «Загрузить».".format(hint))

    def _get_placeable_symbol(self, family, fi=None):
        symbols = self._symbols_for_family(family)
        if not symbols:
            return None
        if fi is not None:
            want = _normalize_family_key(fi.name)
            for sym in symbols:
                if _normalize_family_key(_revit_name(sym)) == want:
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
        if symbols:
            return symbols
        for sym in FilteredElementCollector(self.doc).OfClass(RevitFamilySymbol):
            try:
                sym_fam = _symbol_family(sym)
                if sym_fam is not None and sym_fam.Id == family.Id:
                    symbols.append(sym)
            except Exception:
                continue
        return symbols

    def _get_family_symbol(self, fi):
        """Load .rfa if needed and return a FamilySymbol ready to place."""
        t = Transaction(self.doc, u"Load family")
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
                    u"У семейства «{}» нет типоразмеров для размещения".format(
                        _revit_name(fam)))
            if not symbol.IsActive:
                symbol.Activate()
            t.Commit()
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
            self._set_status(u"Нет активного вида — откройте вид в проекте.")
            return
        try:
            symbol = self._get_family_symbol(fi)
        except Exception as ex:
            self._set_status(u"Ошибка загрузки: {}".format(_as_unicode(ex)))
            return
        if symbol is None:
            self._set_status(
                u"Не удалось подготовить семейство к размещению: {}".format(
                    fi.name))
            return
        search_query = u""
        if self.ui is not None:
            search_query = _as_unicode(self.ui.SearchBox.Text).strip()
        self._reopen_ui_state = {
            "scope": list(self._folder_scope),
            "label": self._folder_scope_label,
            "tree_tag": self._current_tree_tag(),
            "search_query": search_query,
        }
        self._pending_symbol_id = symbol.Id.IntegerValue
        self._pending_family_name = _as_unicode(fi.name)
        self._pending_family_path = os.path.normpath(fi.path)
        self.win.Close()

    def _count_family_instances(self, family_id):
        if family_id is None:
            return 0
        want = family_id.IntegerValue
        n = 0
        for inst in FilteredElementCollector(self.doc).OfClass(RDB.FamilyInstance):
            try:
                sym = getattr(inst, "Symbol", None)
                fam = _symbol_family(sym) if sym is not None else None
                if fam is not None and fam.Id.IntegerValue == want:
                    n += 1
            except Exception:
                continue
        return n

    def _run_pending_placement(self, sym_id, family_name, family_path):
        uidoc = revit.uidoc
        if uidoc is None or uidoc.ActiveView is None or not sym_id:
            return u""
        try:
            symbol = self.doc.GetElement(ElementId(int(sym_id)))
            if symbol is None:
                return u"Семейство не найдено в проекте"
            if not symbol.IsActive:
                t = Transaction(self.doc, u"Activate family type")
                t.Start()
                symbol.Activate()
                t.Commit()
            fam = _symbol_family(symbol)
            before = self._count_family_instances(
                fam.Id if fam is not None else None)
            try:
                uidoc.PromptForFamilyInstancePlacement(symbol)
            except OperationCanceledException:
                pass
            after = self._count_family_instances(
                fam.Id if fam is not None else None)
            if after > before and family_path:
                config.add_recent(family_path)
                self.cfg = config.load()
                libcache._log(u"recent added after place: {}".format(
                    family_path))
                return u"Размещено: {}".format(family_name)
            if after > before:
                return u"Размещено: {}".format(family_name)
            return u"Размещение отменено"
        except Exception as ex:
            return u"Ошибка размещения: {}".format(ex)

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
            libcache._log(u"pump_ui: {}".format(_as_unicode(ex)))
        try:
            import System.Threading
            System.Threading.Thread.Sleep(200)
        except Exception:
            pass

    def _load_families(self, paths):
        t = None
        loaded = []
        skipped = []
        errors = []
        label = paths[0] if len(paths) == 1 else u"{} families".format(len(paths))
        try:
            t = Transaction(self.doc, u"Load Family: {}".format(label))
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
            self._set_status(u"Ошибка: {}".format(str(ex)))
            return

        parts = []
        if loaded:
            parts.append(u"Загружено семейств: {}".format(len(loaded)))
        if skipped:
            parts.append(u"Уже в проекте: {}".format(len(skipped)))
        if errors:
            parts.append(u"Не загружено (ошибки): {}".format(len(errors)))
        self._set_status(u"  |  ".join(parts) if parts else u"Готово.")

    def _on_settings(self, sender, e):
        dlg = FolderBrowserDialog()
        dlg.Description = u"Корневая папка библиотеки семейств Revit (одна библиотека)"
        current = self._library_path()
        if current and os.path.isdir(current):
            dlg.SelectedPath = current
        result = dlg.ShowDialog()
        if result == DialogResult.OK:
            config.set_library_path(dlg.SelectedPath)
            config.clear_recent()
            self.cfg = config.load()
            clear_library_cache()
            self._preview_mem = {}
            self._preview_miss = set()
            self._preview_gen += 1
            self._schedule_scan()

    def _on_reload(self, sender, e):
        if not self._library_path():
            self._set_status(
                u"Путь к библиотеке не задан. Нажмите «Библиотека».")
            return
        config.clear_recent()
        self.cfg = config.load()
        clear_library_cache()
        self._preview_mem = {}
        self._preview_miss = set()
        self._preview_gen += 1
        self._card_build_gen += 1
        self._browse_disk_only = True
        self._scan = {"roots": [], "all": [], "index": {}}
        self._folder_scope = []
        self._folder_scope_label = u""
        if self.ui is not None:
            self._build_tree(self._scan)
            self._show_recents_default()
        self._set_status(u"Сканирование библиотеки\u2026")
        self._schedule_scan()

    def _set_status(self, text):
        if self.ui is not None:
            self.ui.StatusText.Text = text

    def _set_breadcrumb(self, text):
        if self.ui is not None:
            self.ui.BreadcrumbText.Text = text

    def show(self):
        first_open = True
        while True:
            self._init_window()
            if first_open:
                self._set_status(u"Открытие\u2026")
                self._start_initial_load()
                first_open = False
            else:
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
# pyRevit runs scripts directly - no __main__ guard needed
# ---------------------------------------------------------------------------
dlg = FamilyManagerDialog()
dlg.show()
