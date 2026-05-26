# -*- coding: utf-8 -*-
"""Search slash commands."""
from __future__ import print_function

import shortcuts_catalog

_COMMANDS = [
    {
        "key": u"slash:family_browser",
        "title": u"/familybrowser",
        "command_id": u"CustomCtrl_%CustomCtrl_%AVRO%Tools%FamilyBrowser",
        "action": u"family_browser",
    },
    {
        "key": u"slash:clear_all_history",
        "title": u"/searchreset",
        "command_id": u"",
        "action": u"clear_all_history",
    },
]

_catalog_cache = None


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


def _base_catalog():
    out = {}
    for entry in shortcuts_catalog.get_catalog():
        cid = _u(entry.get("command_id"))
        if cid and cid not in out:
            out[cid] = entry
    return out


def clear_runtime_cache():
    global _catalog_cache
    _catalog_cache = None


def get_catalog():
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache

    base = _base_catalog()
    out = []
    for raw in _COMMANDS:
        command_id = _u(raw.get("command_id"))
        title = _u(raw.get("title"))
        source = base.get(command_id, {})
        path_label = u""
        display = title
        keywords = [title, title.lstrip(u"/"), _u(source.get("search_title"))]
        out.append({
            "key": _u(raw.get("key")),
            "command_id": command_id,
            "search_title": title,
            "path_label": path_label,
            "display": display,
            "title": title,
            "full_name": title,
            "group": u"/",
            "paths": _u(source.get("paths")),
            "action": _u(raw.get("action")),
            "keywords": [_norm(x) for x in keywords if _u(x)],
        })

    _catalog_cache = out
    return _catalog_cache


def _score_entry(entry, query):
    title = _norm(entry.get("search_title") or entry.get("title"))
    body = title[1:] if title.startswith(u"/") else title
    if query == u"/":
        return 100
    if title == query:
        return 100
    if title.startswith(query):
        return 90
    if query.startswith(u"/"):
        body_query = query[1:]
        if body_query and body == body_query:
            return 85
        if body_query and body.startswith(body_query):
            return 80
        if body_query and body_query in body:
            return 70
    return 0


def search(query, limit=120):
    q = _norm(query)
    if not q.startswith(u"/"):
        return []
    scored = []
    for entry in get_catalog():
        score = _score_entry(entry, q)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda x: (-x[0], x[1].get("display", u"")))
    return [entry for _, entry in scored[:limit]]
