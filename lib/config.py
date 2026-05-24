# -*- coding: utf-8 -*-
"""
Config manager for AVRO pyRevit extension.
Settings: %APPDATA%\\pyRevit\\AVRO\\config.json
Recent families: %APPDATA%\\pyRevit\\AVRO\\recent_families.json (separate file)
"""
import os
import json
import codecs
import time

CONFIG_DIR  = os.path.join(os.getenv("APPDATA", ""), "pyRevit", "AVRO")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
RECENT_FILE = os.path.join(CONFIG_DIR, "recent_families.json")
LOG_FILE    = os.path.join(CONFIG_DIR, "cache.log")

APP_NAME = u"Диспетчер семейств"

DEFAULTS = {
    "library_path": "",
    "thumbnail_size": 156,
    "recent_families": [],
    "library_cache_hash": "",
    "library_cache_count": 0,
    "ui_theme": "light",
    "ui_language": "en",            # "ru" after user picks Russian in Settings → OK
}

_RECENTS_MIGRATED = False


def _ensure_dir():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)


def _log(msg):
    try:
        _ensure_dir()
        line = u"[{}] {}\n".format(
            time.strftime("%Y-%m-%d %H:%M:%S"), _u(msg))
        with codecs.open(LOG_FILE, "a", "utf-8") as f:
            f.write(line)
    except Exception:
        pass


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


def _atomic_write_text(path, text):
    """Write UTF-8 text via temp file (IronPython / Windows safe)."""
    _ensure_dir()
    tmp = path + u".tmp"
    with codecs.open(tmp, "w", "utf-8") as f:
        f.write(text)
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    try:
        os.rename(tmp, path)
    except Exception:
        with codecs.open(path, "w", "utf-8") as f:
            f.write(text)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def _migrate_recents_from_config():
    global _RECENTS_MIGRATED
    if _RECENTS_MIGRATED:
        return
    _RECENTS_MIGRATED = True
    if os.path.exists(RECENT_FILE):
        return
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        with codecs.open(CONFIG_FILE, "r", "utf-8") as f:
            data = json.load(f)
        old = data.get("recent_families") or []
        if old:
            save_recents(old)
            _log(u"recents migrated from config.json ({} paths)".format(
                len(old)))
    except Exception as ex:
        _log(u"recents migrate failed: {}".format(_u(ex)))


def load_recents():
    """Last-used .rfa paths (newest first), from dedicated JSON file."""
    _ensure_dir()
    _migrate_recents_from_config()
    if not os.path.exists(RECENT_FILE):
        return []
    try:
        with codecs.open(RECENT_FILE, "r", "utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return [_u(p) for p in data if p]
    except Exception as ex:
        _log(u"recents load failed: {}".format(_u(ex)))
        return []


def save_recents(paths):
    """Persist recent list only — never touches config.json."""
    paths = [_u(p) for p in (paths or []) if p][:20]
    try:
        text = json.dumps(paths, ensure_ascii=False, indent=2)
    except Exception:
        text = json.dumps(
            [p.encode("utf-8") if isinstance(p, unicode) else p for p in paths],
            ensure_ascii=True, indent=2)
    if isinstance(text, str):
        text = _u(text)
    _atomic_write_text(RECENT_FILE, text)


def _normalize_library_cfg(cfg):
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


def _save_config_core(data):
    """Write config.json; merge onto existing file so fields are not lost."""
    _ensure_dir()
    data = _normalize_library_cfg(dict(data))
    stored = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with codecs.open(CONFIG_FILE, "r", "utf-8") as f:
                on_disk = json.load(f)
            if isinstance(on_disk, dict):
                stored.update(on_disk)
        except Exception:
            pass
    for k in DEFAULTS:
        if k == "recent_families":
            continue
        v = data.get(k, DEFAULTS[k])
        if k == "library_path":
            v = _u(v)
        stored[k] = v
    stored.pop("ui_language_override", None)
    try:
        text = json.dumps(stored, ensure_ascii=False, indent=2)
    except Exception:
        text = json.dumps(stored, ensure_ascii=True, indent=2)
    if isinstance(text, str):
        text = _u(text)
    _atomic_write_text(CONFIG_FILE, text)


def read_ui_language():
    """Read ``ui_language`` directly from config.json (no ``load()`` side effects)."""
    if not os.path.exists(CONFIG_FILE):
        return u"en"
    try:
        with codecs.open(CONFIG_FILE, "r", "utf-8") as f:
            data = json.load(f)
        lang = _u(data.get("ui_language", u"en")).strip().lower()
        return u"ru" if lang == u"ru" else u"en"
    except Exception as ex:
        _log(u"read_ui_language failed: {}".format(_u(ex)))
        return u"en"


def get_ui_language():
    """English by default; Russian only when ``ui_language`` is ``ru`` in config."""
    return read_ui_language()


def load():
    """Return config dict. ``recent_families`` always from recent_families.json."""
    _ensure_dir()
    if not os.path.exists(CONFIG_FILE):
        data = dict(DEFAULTS)
    else:
        try:
            with codecs.open(CONFIG_FILE, "r", "utf-8") as f:
                data = json.load(f)
            for k, v in DEFAULTS.items():
                data.setdefault(k, v)
        except Exception:
            data = dict(DEFAULTS)
    data = _normalize_library_cfg(data)
    data["recent_families"] = load_recents()
    return data


def save(cfg):
    """Persist settings to config.json (recents are NOT stored here)."""
    _save_config_core(cfg)


def patch_fields(updates):
    """Update only known keys in config.json; never touches recents file."""
    if not updates:
        return
    cfg = load()
    for key, val in updates.items():
        if key not in DEFAULTS or key == "recent_families":
            continue
        cfg[key] = val
    save(cfg)


def set_value(key, value):
    if key == "recent_families":
        save_recents(value or [])
        return
    cfg = load()
    cfg[key] = value
    save(cfg)


def set_library_path(path):
    cfg = load()
    cfg["library_path"] = path or ""
    save(cfg)


def add_recent(rfa_path):
    import library_cache as _lc
    rfa_path = _lc._norm_path(rfa_path)
    if not rfa_path:
        _log(u"add_recent: empty path")
        return False
    recent = [_lc._norm_path(p) for p in load_recents()]
    if rfa_path in recent:
        recent.remove(rfa_path)
    recent.insert(0, rfa_path)
    recent = recent[:20]
    save_recents(recent)
    ok = rfa_path in load_recents()
    _log(u"add_recent path={} count={} ok={}".format(
        rfa_path, len(recent), ok))
    return ok


def clear_recent():
    save_recents([])
    _log(u"recents cleared")
