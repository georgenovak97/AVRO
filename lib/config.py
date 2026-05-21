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

APP_NAME = u"Диспетчер семейств"

DEFAULTS = {
    "library_path": "",           # единственная корневая папка библиотеки
    "thumbnail_size": 156,
    "recent_families": [],        # last 20 loaded .rfa paths
    "library_cache_hash": "",     # md5 of library path, set after scan
    "library_cache_count": 0,
    "ui_theme": "light",          # light | dark
}


def _ensure_dir():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)


def _normalize_library_cfg(cfg):
    """Одна библиотека: миграция со старых library_paths / last_path."""
    path = (cfg.get("library_path") or u"").strip()
    if not path:
        path = (cfg.get("last_path") or u"").strip()
    if not path:
        legacy = cfg.get("library_paths") or []
        if isinstance(legacy, basestring):
            path = legacy.strip()
        elif legacy:
            path = (legacy[-1] or u"").strip()
    cfg["library_path"] = path
    return cfg


def load():
    """Return config dict. Missing keys filled with defaults."""
    _ensure_dir()
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULTS)
    try:
        with codecs.open(CONFIG_FILE, "r", "utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULTS.items():
            data.setdefault(k, v)
        return _normalize_library_cfg(data)
    except Exception:
        return dict(DEFAULTS)


def _u(text):
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    if isinstance(text, str):
        for enc in ("utf-8", "cp1251", "latin-1"):
            try:
                return unicode(text, enc)
            except Exception:
                continue
    try:
        return unicode(text)
    except Exception:
        return u""


def save(cfg):
    """Persist config dict to disk."""
    _ensure_dir()
    cfg = _normalize_library_cfg(dict(cfg))
    stored = dict(DEFAULTS)
    for k in DEFAULTS:
        v = cfg.get(k, DEFAULTS[k])
        if k == "library_path":
            v = _u(v)
        elif k == "recent_families":
            v = [_u(p) for p in (v or []) if p]
        stored[k] = v
    text = json.dumps(stored, ensure_ascii=True, indent=2)
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


def get_library_path():
    return load().get("library_path", "") or ""


def set_library_path(path):
    """Заменить единственный путь к библиотеке (кнопка «Библиотека»)."""
    cfg = load()
    cfg["library_path"] = path or ""
    save(cfg)


def add_library_path(path):
    """Совместимость: то же, что set_library_path."""
    set_library_path(path)


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
