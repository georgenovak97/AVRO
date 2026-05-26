# -*- coding: utf-8 -*-
"""Search catalog from ``keys/<layout>/<version_layout>/KeyboardShortcuts.xml``."""
from __future__ import print_function

import revit_context
import shortcut_xml
import command_runner

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


def _norm_token(text):
    return _u(text).strip().lower().replace(u"ё", u"е")


def refresh_available_cache():
    global _catalog_cache
    _catalog_cache = {}


def build_catalog(profile_info=None):
    info = profile_info or revit_context.get_profile_info()
    if not info.get("xml_exists"):
        return []
    entries = shortcut_xml.load_entries(info.get("xml_path"), info.get("profile_key"))
    entries = [
        entry for entry in entries
        if command_runner.is_command_available(entry.get("command_id"))
    ]
    entries.sort(key=lambda e: _norm_token(e.get("display")))
    return entries


def get_catalog():
    global _catalog_cache
    info = revit_context.get_profile_info()
    profile_key = info.get("profile_key")
    if profile_key not in _catalog_cache:
        _catalog_cache[profile_key] = build_catalog(info)
    return _catalog_cache.get(profile_key, [])
