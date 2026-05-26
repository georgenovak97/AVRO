# -*- coding: utf-8 -*-
"""Load Search command catalog from keyboard shortcuts XML."""
from __future__ import print_function

import xml.etree.ElementTree as ET


def _u(text):
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    try:
        return unicode(text)
    except Exception:
        return unicode(str(text), "utf-8", "ignore")


def _norm(text):
    return _u(text).strip().lower().replace(u"ё", u"е")


def _search_title_from_command_name(name):
    text = _u(name)
    parts = [part.strip() for part in text.split(u";") if part.strip()]
    first = parts[0] if parts else text
    if u":" not in first:
        return first
    segs = [seg.strip() for seg in first.split(u":") if seg.strip()]
    if not segs:
        return first
    base = segs[0]
    last = segs[-1]
    return base + u": " + last if last and last != base else base


def _path_label_from_paths(paths):
    text = _u(paths)
    if not text:
        return u""
    first = text.split(u";")[0].strip()
    return first.replace(u">", u" | ")


def _group_from_paths(paths):
    text = _u(paths)
    if not text:
        return u"Все"
    first = text.split(u";")[0].strip()
    seg = first.split(u">")[0].strip()
    return seg or u"Все"


def _keywords_from_search_title(search_title):
    kw = []
    seen = set()
    full = _norm(search_title)
    if len(full) >= 2:
        kw.append(full)
        seen.add(full)
    for word in _u(search_title).split():
        token = _norm(word)
        if len(token) >= 2 and token not in seen:
            kw.append(token)
            seen.add(token)
    return kw


def _make_key(profile_key, command_id, command_name, paths):
    return u"{}|{}|{}|{}".format(
        _u(profile_key),
        _u(command_id).strip(),
        _u(command_name).strip(),
        _u(paths).strip(),
    )


def load_entries(xml_path, profile_key):
    try:
        root = ET.parse(xml_path).getroot()
    except Exception:
        return []

    entries = []
    for item in root.findall(".//ShortcutItem"):
        command_id = _u(item.get("CommandId")).strip()
        command_name = _u(item.get("CommandName")).strip()
        paths = _u(item.get("Paths")).strip()
        if not command_id or not command_name:
            continue

        search_title = _search_title_from_command_name(command_name)
        path_label = _path_label_from_paths(paths)
        display = search_title if not path_label else search_title + u" - " + path_label

        entries.append({
            "key": _make_key(profile_key, command_id, command_name, paths),
            "command_id": command_id,
            "search_title": search_title,
            "path_label": path_label,
            "display": display,
            "title": search_title,
            "full_name": command_name,
            "group": _group_from_paths(paths),
            "paths": paths,
            "keywords": _keywords_from_search_title(search_title),
            "profile_key": _u(profile_key),
        })
    return entries
