# -*- coding: utf-8 -*-
"""
Persist library scan index to disk (survives pyRevit script reload).

Stores plain dicts only (pickle-safe). Files:
  library_meta.json   - quick validation
  library_index.pkl   - quick load
  library_index.json  - backup / legacy
"""
import os
import json
import hashlib
import codecs
import threading
import glob

import config
import avro_log
import family_scanner as scanner

try:
    import cPickle as pickle
except ImportError:
    import pickle

CACHE_VERSION = 1
META_FILE = os.path.join(config.CONFIG_DIR, "library_meta.json")
PICKLE_FILE = os.path.join(config.CONFIG_DIR, "library_index.pkl")
INDEX_FILE = os.path.join(config.CONFIG_DIR, "library_index.json")
LOG_FILE = os.path.join(config.CONFIG_DIR, "cache.log")
PREVIEW_MISS_VERSION = 1
_CACHE_IO_LOCK = threading.RLock()


def _log(msg):
    avro_log.write("library_cache", msg)


def _u(text):
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    if isinstance(text, str):
        for enc in ("utf-8", "cp1251"):
            try:
                return unicode(text, enc)
            except Exception:
                continue
        try:
            return unicode(text, "latin-1")
        except Exception:
            return unicode(repr(text))
    try:
        return unicode(text)
    except Exception:
        return u""


def _repair_mojibake(text):
    """Fix UTF-8 Cyrillic mis-decoded as Latin-1 (common after pickle/json reload)."""
    s = _u(text)
    if not s:
        return s
    try:
        if any(ord(c) >= 0xC2 for c in s):
            fixed = s.encode("latin-1").decode("utf-8")
            if fixed and fixed != s:
                return fixed
    except Exception:
        pass
    return s


def _sanitize_value(val):
    if isinstance(val, dict):
        out = {}
        for k, v in val.items():
            out[_u(k)] = _sanitize_value(v)
        return out
    if isinstance(val, list):
        return [_sanitize_value(x) for x in val]
    if isinstance(val, tuple):
        return tuple(_sanitize_value(x) for x in val)
    if isinstance(val, (str, unicode)):
        return _u(val)
    return val


def _unicode_to_utf8(val):
    """IronPython 2: pickle/json safe tree (only utf-8 byte strings)."""
    if isinstance(val, dict):
        out = {}
        for k, v in val.items():
            out[_unicode_to_utf8(_u(k))] = _unicode_to_utf8(v)
        return out
    if isinstance(val, list):
        return [_unicode_to_utf8(x) for x in val]
    if isinstance(val, tuple):
        return tuple(_unicode_to_utf8(x) for x in val)
    if isinstance(val, unicode):
        return val.encode("utf-8")
    if isinstance(val, str):
        try:
            return _u(val).encode("utf-8")
        except Exception:
            return val
    return val


def _utf8_to_unicode(val):
    """Restore tree after pickle/json load."""
    if isinstance(val, unicode):
        return val
    if isinstance(val, dict):
        out = {}
        for k, v in val.items():
            out[_utf8_to_unicode(k)] = _utf8_to_unicode(v)
        return out
    if isinstance(val, list):
        return [_utf8_to_unicode(x) for x in val]
    if isinstance(val, tuple):
        return tuple(_utf8_to_unicode(x) for x in val)
    if isinstance(val, str):
        try:
            return unicode(val, "utf-8")
        except Exception:
            return _repair_mojibake(val)
    return val


def _norm_path(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(_u(path))))


def cache_key(paths):
    """Build cache key from configured paths (no isdir check)."""
    norm = []
    for p in paths or []:
        if not p:
            continue
        norm.append(_norm_path(p))
    return tuple(sorted(norm))


def key_hash(key_tuple):
    if not key_tuple:
        return u""
    raw = u"|".join(_u(p) for p in key_tuple).encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def preview_miss_file(key_tuple):
    """Return the small persistent negative-preview cache for one library."""
    kh = key_hash(key_tuple)
    if not kh:
        return None
    return os.path.join(config.CONFIG_DIR, "preview_miss_{}.json".format(kh))


def _normalize_preview_misses(entries):
    """Normalize path->mtime entries; legacy path-only entries are ignored."""
    if not isinstance(entries, dict):
        return {}
    result = {}
    for path, value in entries.items():
        path = _norm_path(path)
        if not path or not isinstance(value, dict):
            continue
        try:
            mtime = float(value.get("mtime"))
            size = int(value.get("size"))
        except (TypeError, ValueError):
            continue
        if mtime < 0 or size < 0:
            continue
        result[path] = {"mtime": mtime, "size": size}
    return result


def load_preview_misses(key_tuple):
    """Load validated-format negative preview entries for a library key."""
    path = preview_miss_file(key_tuple)
    if not path or not os.path.isfile(path):
        return {}
    try:
        with codecs.open(path, "r", "utf-8") as f:
            data = json.load(f)
        if data.get("version") != PREVIEW_MISS_VERSION:
            return {}
        if data.get("key_hash") != key_hash(key_tuple):
            return {}
        return _normalize_preview_misses(data.get("entries"))
    except Exception as ex:
        _log(u"preview miss load failed: {}".format(ex))
        return {}


def save_preview_misses(key_tuple, entries):
    """Atomically save a compact negative preview cache for one library key."""
    path = preview_miss_file(key_tuple)
    if not path:
        return False
    normalized = _normalize_preview_misses(entries)
    payload = {
        "version": PREVIEW_MISS_VERSION,
        "key_hash": key_hash(key_tuple),
        "entries": normalized,
    }
    tmp = path + u".tmp"
    with _CACHE_IO_LOCK:
        try:
            config._ensure_dir()
            _write_json_file(tmp, payload, indent=2)
            if os.path.isfile(path):
                os.remove(path)
            os.rename(tmp, path)
            return True
        except Exception as ex:
            _log(u"preview miss save failed: {}".format(ex))
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            return False


def clear_preview_misses(key_tuple):
    """Remove the persistent negative preview cache for a library key."""
    path = preview_miss_file(key_tuple)
    if not path:
        return
    with _CACHE_IO_LOCK:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except Exception as ex:
            _log(u"preview miss clear failed: {}".format(ex))


def _collect_dir_mtimes(root_path, max_depth=2):
    """Collect (norm_path, mtime) strings for root and up to max_depth subdirectories."""
    mtimes = []
    root_np = _norm_path(root_path)
    try:
        root_mtime = int(os.path.getmtime(root_np))
        mtimes.append(u"{}:{}".format(root_np, root_mtime))
    except Exception:
        mtimes.append(root_np)
        return mtimes

    if not os.path.isdir(root_np):
        return mtimes

    try:
        root_abs = os.path.abspath(root_np)
        for base, dirs, _files in os.walk(root_abs):
            dirs.sort(key=lambda s: s.lower())
            rel = os.path.relpath(base, root_abs)
            if rel == ".":
                depth = 0
            else:
                depth = rel.count(os.sep) + 1
            if depth >= max_depth:
                del dirs[:]
            if depth > 0:
                norm_base = _norm_path(base)
                try:
                    mtimes.append(u"{}:{}".format(norm_base, int(os.path.getmtime(base))))
                except Exception:
                    mtimes.append(norm_base)
    except Exception:
        pass
    return mtimes


def library_fingerprint(key_tuple):
    """Changes when library folder or subfolder mtime changes (cheap stale hint)."""
    parts = []
    for p in key_tuple or []:
        parts.extend(_collect_dir_mtimes(p, max_depth=2))
    if not parts:
        return u""
    return hashlib.md5(u"|".join(parts).encode("utf-8")).hexdigest()


def cache_available(key_tuple):
    """True if meta + index exist and match the library key (no full parse)."""
    if not key_tuple:
        return False
    kh = key_hash(key_tuple)
    fp = library_fingerprint(key_tuple)
    meta = _read_meta()
    if not meta or meta.get("key_hash") != kh:
        return False
    saved_fp = meta.get("library_fingerprint")
    if saved_fp and fp and saved_fp != fp:
        _log(u"cache stale: fingerprint mismatch {} vs {}".format(saved_fp, fp))
        return False
    if os.path.isfile(PICKLE_FILE) or os.path.isfile(INDEX_FILE):
        return True
    return False


def _serialize_node(node):
    return {
        "path": _u(node.path),
        "name": _u(node.name),
        "family_paths": [_u(fi.path) for fi in node.families],
        "children": [
            _serialize_node(node.children[name])
            for name in sorted(node.children.keys(), key=lambda s: s.lower())
        ],
    }


def _deserialize_node(data, fi_by_path):
    node = scanner.FolderNode(_norm_path(data["path"]), data.get("name"))
    for p in data.get("family_paths", []):
        fi = fi_by_path.get(_norm_path(p))
        if fi is None:
            fi = fi_by_path.get(p)
        if fi is not None:
            node.families.append(fi)
    for child_data in data.get("children", []):
        child = _deserialize_node(child_data, fi_by_path)
        node.children[child.name] = child
    return node


def _serialize_family(fi):
    return {
        "path": _u(fi.path),
        "name": _u(fi.name),
        "category": _u(fi.category),
        "size_kb": fi.size_kb,
        "modified": _u(fi.modified),
        "folder": _u(fi.folder),
        "library_root": _u(fi.library_root),
        "rel_path": _u(fi.rel_path),
        "revit_version": _u(getattr(fi, "revit_version", u"")),
    }


def _deserialize_family(rec):
    path = _norm_path(rec.get("path"))
    if not path:
        return None
    fi = scanner.FamilyInfo.__new__(scanner.FamilyInfo)
    fi.path = path
    default_name = os.path.splitext(os.path.basename(path))[0]
    fi.name = _repair_mojibake(rec.get("name", default_name))
    fi.size_kb = rec.get("size_kb", 0)
    fi.modified = _repair_mojibake(rec.get("modified", ""))
    fi.folder = _repair_mojibake(
        rec.get("folder", os.path.basename(os.path.dirname(path))))
    fi.library_root = _norm_path(rec.get("library_root")) if rec.get("library_root") else u""
    fi.rel_path = _repair_mojibake(rec.get("rel_path", fi.folder))
    # Recompute from path so old caches (e.g. "Furniture" from desktop/table) recover
    fi.category = scanner.category_from_path(path, fi.library_root) or _repair_mojibake(
        rec.get("category", "Generic Models"))
    fi.revit_version = _repair_mojibake(rec.get("revit_version", u""))
    fi.preview = None
    return fi


def _blob_from_scan(scan, preview_miss):
    return {
        "version": CACHE_VERSION,
        "key_hash": None,
        "families": [_serialize_family(fi) for fi in scan.get("all", [])],
        "roots": [_serialize_node(r) for r in scan.get("roots", [])],
        "preview_miss": sorted(_norm_path(p) for p in (preview_miss or [])),
    }


def _scan_from_blob(blob):
    if not blob or blob.get("version") != CACHE_VERSION:
        return None, set()
    fi_by_path = {}
    all_families = []
    for rec in blob.get("families", []):
        fi = _deserialize_family(rec)
        if fi is None:
            continue
        fi_by_path[fi.path] = fi
        all_families.append(fi)
    if not all_families:
        return None, set()
    roots = []
    for root_data in blob.get("roots", []):
        roots.append(_deserialize_node(root_data, fi_by_path))
    all_families.sort(key=lambda f: f.name.lower())
    for node in scanner.index_folder_tree(roots).values():
        node.families.sort(key=lambda f: f.name.lower())
    scanner.finalize_folder_counts(roots)
    preview_miss = set(_norm_path(p) for p in blob.get("preview_miss", []))
    scan = {
        "roots": roots,
        "all": all_families,
        "index": scanner.index_folder_tree(roots),
    }
    return scan, preview_miss


def _write_json_file(path, data, indent=None):
    """Write JSON as UTF-8 file with ASCII escapes — safe on IronPython 2."""
    data = _unicode_to_utf8(_sanitize_value(data))
    kwargs = {"ensure_ascii": True, "separators": (",", ":")}
    if indent is not None:
        kwargs["indent"] = indent
        kwargs.pop("separators", None)
    try:
        text = json.dumps(data, **kwargs)
    except Exception:
        # Fallback: manual ascii-only via unicode-escape style strings
        text = json.dumps(_sanitize_value(data), ensure_ascii=True)
    if isinstance(text, unicode):
        text = text.encode("utf-8")
    with open(path, "wb") as f:
        f.write(text)


def _write_meta(key_tuple, count):
    meta = {
        "version": CACHE_VERSION,
        "key": [_u(p) for p in key_tuple],
        "key_hash": key_hash(key_tuple),
        "family_count": count,
        "library_fingerprint": library_fingerprint(key_tuple),
    }
    _write_json_file(META_FILE, meta, indent=2)


def _read_meta():
    if not os.path.isfile(META_FILE):
        return None
    try:
        with codecs.open(META_FILE, "r", "utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save(key_tuple, scan, preview_miss=None, write_json=True):
    if not key_tuple or not scan or not scan.get("all"):
        _log(u"save skipped: empty key or scan")
        return False, u"empty_scan"

    config._ensure_dir()
    kh = key_hash(key_tuple)
    blob = _blob_from_scan(scan, preview_miss)
    blob["key"] = [_u(p) for p in key_tuple]
    blob["key_hash"] = kh
    blob["library_fingerprint"] = library_fingerprint(key_tuple)
    blob = _sanitize_value(blob)

    ok_json = False
    err_json = u""
    if write_json:
        try:
            tmpj = INDEX_FILE + u".tmp"
            _write_json_file(tmpj, blob, indent=None)
            if os.path.isfile(INDEX_FILE):
                try:
                    os.remove(INDEX_FILE)
                except Exception:
                    pass
            os.rename(tmpj, INDEX_FILE)
            ok_json = os.path.isfile(INDEX_FILE)
        except Exception as ex:
            err_json = unicode(ex)
            try:
                if os.path.isfile(tmpj):
                    os.remove(tmpj)
            except Exception:
                pass

    ok_pkl = False
    err_pkl = u""
    if ok_json:
        try:
            blob_store = _unicode_to_utf8(blob)
            tmp = PICKLE_FILE + u".tmp"
            with open(tmp, "wb") as f:
                pickle.dump(blob_store, f, protocol=2)
            if os.path.isfile(PICKLE_FILE):
                try:
                    os.remove(PICKLE_FILE)
                except Exception:
                    pass
            os.rename(tmp, PICKLE_FILE)
            ok_pkl = os.path.isfile(PICKLE_FILE)
        except Exception as ex:
            err_pkl = unicode(ex)
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    if ok_json or ok_pkl:
        try:
            _write_meta(key_tuple, len(scan["all"]))
        except Exception as ex:
            _log(u"meta write failed: {}".format(ex))

    if ok_json:
        _log(u"save ok json {} families hash {}".format(
            len(scan["all"]), kh))
        return True, u"ok_json"
    if ok_pkl:
        _log(u"save ok pickle {} families hash {}".format(
            len(scan["all"]), kh))
        return True, u"ok"

    msg = u"json:{} pickle:{}".format(err_json, err_pkl)
    _log(u"save FAILED {}".format(msg))
    return False, msg


def save(key_tuple, scan, preview_miss=None, write_json=True):
    """Serialize one cache write at a time.

    Scan completion and window cleanup can request persistence concurrently.
    The fixed IronPython-compatible temporary names are safe only while this
    lock is held.
    """
    with _CACHE_IO_LOCK:
        return _save(key_tuple, scan, preview_miss, write_json)


def _load_blob_file(path):
    if path.endswith(".pkl"):
        with open(path, "rb") as f:
            raw = pickle.load(f)
        return _utf8_to_unicode(raw)
    with codecs.open(path, "r", "utf-8") as f:
        raw = json.load(f)
    return _utf8_to_unicode(raw)


def load(key_tuple):
    if not key_tuple:
        return None, set(), u"no_library_path"

    kh = key_hash(key_tuple)
    meta = _read_meta()
    if meta and meta.get("key_hash") == kh:
        _log(u"meta hash match count {}".format(meta.get("family_count")))

    blob = None
    src = u""
    if os.path.isfile(INDEX_FILE):
        try:
            blob = _load_blob_file(INDEX_FILE)
            src = u"json"
        except Exception as ex:
            _log(u"json load error: {}".format(ex))
            blob = None

    if blob is None and os.path.isfile(PICKLE_FILE):
        try:
            blob = _load_blob_file(PICKLE_FILE)
            src = u"pkl"
        except Exception as ex:
            _log(u"pkl load error: {}".format(ex))
            blob = None

    if blob is None:
        _log(u"load: no cache files")
        return None, set(), u"no_cache_file"

    if blob.get("key_hash") != kh:
        _log(u"load: hash mismatch file={} want={}".format(
            blob.get("key_hash"), kh))
        return None, set(), u"key_mismatch"

    scan, preview_miss = _scan_from_blob(blob)
    if scan is None:
        _log(u"load: empty families from {}".format(src))
        return None, set(), u"empty_cache"

    fp = library_fingerprint(key_tuple)
    saved_fp = (meta or {}).get("library_fingerprint") or blob.get("library_fingerprint")
    if saved_fp and fp and saved_fp != fp:
        _log(u"load rejected: library folder changed since cache {} vs {}".format(
            saved_fp, fp))
        return None, set(), u"stale_cache"

    _log(u"load ok from {} : {} families".format(src, len(scan["all"])))
    return scan, preview_miss, None


def clear():
    with _CACHE_IO_LOCK:
        for path in (META_FILE, PICKLE_FILE, PICKLE_FILE + u".tmp",
                     INDEX_FILE, INDEX_FILE + u".tmp"):
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        for path in glob.glob(os.path.join(
                config.CONFIG_DIR, "preview_miss_*.json*")):
            try:
                os.remove(path)
            except Exception:
                pass
        try:
            import rfa_preview
            rfa_preview.clear_preview_cache()
        except Exception as ex:
            _log(u"preview cache clear failed: {}".format(_u(ex)))
        _log(u"cache cleared")
