# -*- coding: utf-8 -*-
"""Search history, split by Revit version and UI language."""
from __future__ import print_function

import codecs
import json
import os
import time

import config
import revit_context
import shortcuts_catalog
import slash_commands

_MAX = 15
_SEARCH_RECENT_MAX = 200
_TMP_DIR = config.SEARCH_STATE_DIR
_catalog_cache = {}


def _u(text):
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    try:
        return unicode(text)
    except Exception:
        return unicode(str(text), "utf-8", "ignore")


def _profile_key():
    return _u(revit_context.get_profile_info().get("profile_key") or u"DEFAULT")


def _ensure_tmp_dir():
    try:
        if not os.path.isdir(_TMP_DIR):
            os.makedirs(_TMP_DIR)
    except Exception:
        pass


def _state_path(prefix):
    filename = u"{}.{}.json".format(prefix, _profile_key())
    _ensure_tmp_dir()
    return os.path.join(_TMP_DIR, filename)


def clear_runtime_cache():
    global _catalog_cache
    _catalog_cache = {}


def _catalog():
    global _catalog_cache
    profile_key = _profile_key()
    if profile_key in _catalog_cache:
        return _catalog_cache[profile_key]

    out = {}
    for entry in shortcuts_catalog.get_catalog():
        key = entry.get("key")
        if key:
            out[key] = entry
    for entry in slash_commands.get_catalog():
        key = entry.get("key")
        if key:
            out[key] = entry
    _catalog_cache[profile_key] = out
    return out


def _load_list(path):
    if not os.path.isfile(path):
        return []
    try:
        with codecs.open(path, "r", "utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, list):
            return []
        return [_u(x) for x in data if x]
    except Exception:
        return []


def _save_list(path, items, limit):
    try:
        payload = json.dumps(items[:limit], ensure_ascii=False, indent=2)
        if isinstance(payload, str):
            payload = _u(payload)
        config._atomic_write_text(path, payload)
    except Exception:
        pass


def _load_keys():
    return _load_list(_state_path("recent_commands"))


def _save_keys(keys):
    _save_list(_state_path("recent_commands"), keys, _MAX)


def _load_search_recent_keys():
    path = _state_path("search_recent_commands")
    if not os.path.isfile(path):
        return _load_keys()
    return _load_list(path)


def _save_search_recent_keys(keys):
    _save_list(_state_path("search_recent_commands"), keys, _SEARCH_RECENT_MAX)


def _load_rankings():
    path = _state_path("launch_rankings")
    if not os.path.isfile(path):
        return {}
    try:
        with codecs.open(path, "r", "utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            return {}
        out = {}
        for key, value in data.items():
            if not key or not isinstance(value, dict):
                continue
            try:
                count = max(0, int(value.get("count", 0)))
            except Exception:
                count = 0
            try:
                last_used = float(value.get("last_used", 0))
            except Exception:
                last_used = 0
            out[_u(key)] = {
                "count": count,
                "last_used": last_used,
            }
        return out
    except Exception:
        return {}


def _save_rankings(rankings):
    try:
        payload = json.dumps(rankings, ensure_ascii=False, indent=2, sort_keys=True)
        if isinstance(payload, str):
            payload = _u(payload)
        config._atomic_write_text(_state_path("launch_rankings"), payload)
    except Exception:
        pass


def _record_launch_ranking(entry_key):
    rankings = _load_rankings()
    stats = rankings.get(entry_key, {"count": 0, "last_used": 0})
    stats["count"] = int(stats.get("count", 0)) + 1
    stats["last_used"] = time.time()
    rankings[entry_key] = stats
    _save_rankings(rankings)


def record(entry_key):
    key = _u(entry_key)
    if not key:
        return
    keys = _load_keys()
    if key in keys:
        keys.remove(key)
    keys.insert(0, key)
    _save_keys(keys)

    search_keys = _load_search_recent_keys()
    if key in search_keys:
        search_keys.remove(key)
    search_keys.insert(0, key)
    _save_search_recent_keys(search_keys)

    _record_launch_ranking(key)


def remove_search_recent(entry_key):
    key = _u(entry_key)
    if not key:
        return
    keys = _load_search_recent_keys()
    if key not in keys:
        return
    _save_search_recent_keys([item for item in keys if item != key])


def get_launch_rankings():
    return _load_rankings()


def clear_all_history():
    _save_keys([])
    _save_search_recent_keys([])
    _save_rankings({})


def get_search_recent_entries(limit=None):
    catalog = _catalog()
    out = []
    max_items = _SEARCH_RECENT_MAX if limit is None else max(0, int(limit))
    for key in _load_search_recent_keys():
        entry = catalog.get(key)
        if not entry:
            continue
        out.append(entry)
        if len(out) >= max_items:
            break
    return out


def get_history_entries():
    """Up to 15 records for the current profile, newest first."""
    catalog = _catalog()
    out = []
    for key in _load_keys():
        entry = catalog.get(key)
        if not entry:
            continue
        out.append(entry)
        if len(out) >= _MAX:
            break
    return out
