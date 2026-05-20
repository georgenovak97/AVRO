# -*- coding: utf-8 -*-
"""
Config manager for AVRO pyRevit extension.
Stores settings in %APPDATA%\pyRevit\AVRO\config.json
"""
import os
import json
import codecs

CONFIG_DIR  = os.path.join(os.getenv("APPDATA", ""), "pyRevit", "AVRO")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "library_paths": [],          # list of root folder paths
    "last_path": "",
    "thumbnail_size": 156,
    "recent_families": [],        # last 20 loaded .rfa paths
    "library_cache_hash": "",     # md5 of library path(s), set after scan
    "library_cache_count": 0,
}


def _ensure_dir():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)


def load():
    """Return config dict. Missing keys filled with defaults."""
    _ensure_dir()
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULTS)
    try:
        with codecs.open(CONFIG_FILE, "r", "utf-8") as f:
            data = json.load(f)
        # fill missing keys
        for k, v in DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(DEFAULTS)


def save(cfg):
    """Persist config dict to disk."""
    _ensure_dir()
    text = json.dumps(cfg, ensure_ascii=True, indent=2)
    if isinstance(text, unicode):
        text = text.encode("utf-8")
    with open(CONFIG_FILE, "wb") as f:
        f.write(text)


def get(key, default=None):
    return load().get(key, default)


def set_value(key, value):
    cfg = load()
    cfg[key] = value
    save(cfg)


def add_library_path(path):
    cfg = load()
    paths = cfg.get("library_paths", [])
    if path not in paths:
        paths.append(path)
        cfg["library_paths"] = paths
        cfg["last_path"] = path
        save(cfg)


def add_recent(rfa_path):
    import library_cache as _lc
    rfa_path = _lc._norm_path(rfa_path)
    cfg = load()
    recent = [_lc._norm_path(p) for p in cfg.get("recent_families", [])]
    if rfa_path in recent:
        recent.remove(rfa_path)
    recent.insert(0, rfa_path)
    cfg["recent_families"] = recent[:20]
    save(cfg)


def clear_recent():
    """Empty the «Недавние» list (e.g. on full library refresh)."""
    cfg = load()
    cfg["recent_families"] = []
    save(cfg)
