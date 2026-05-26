# -*- coding: utf-8 -*-
"""Search command matching by title, without ribbon path weighting."""
from __future__ import print_function

import recent_history
import shortcuts_catalog
import slash_commands


def _norm(text):
    if text is None:
        return u""
    if not isinstance(text, unicode):
        try:
            text = unicode(text)
        except Exception:
            text = unicode(str(text), "utf-8", "ignore")
    return text.strip().lower().replace(u"ё", u"е")


def _score_entry(entry, query):
    if not query:
        return 1
    title = _norm(entry.get("search_title") or entry.get("title"))
    keywords = [_norm(k) for k in entry.get("keywords", [])]

    if title == query:
        return 100
    if title.startswith(query):
        return 90
    if query in title:
        return 80
    for kw in keywords:
        if kw == query:
            return 75
        if kw.startswith(query):
            return 65
        if query in kw:
            return 55
    return 0


def _copy_entry(entry, bucket):
    out = dict(entry)
    out["_bucket"] = bucket
    return out


def _rank_stats(entry, rankings):
    stats = rankings.get(entry.get("key"), {})
    return (
        int(stats.get("count", 0) or 0),
        float(stats.get("last_used", 0) or 0),
    )


def _ranking_sort_key(score, entry, rankings):
    count, last_used = _rank_stats(entry, rankings)
    return (
        -count,
        -last_used,
        -score,
        _norm(entry.get("path_label")),
        _norm(entry.get("search_title") or entry.get("title")),
        _norm(entry.get("display")),
    )


def search(query, group=None, limit=120):
    q = _norm(query)
    if q.startswith(u"/"):
        return slash_commands.search(query, limit=limit)
    catalog = shortcuts_catalog.get_catalog()
    rankings = recent_history.get_launch_rankings()
    if group and _norm(group) not in (_norm(u"Все"), _norm(u"All")):
        catalog = [e for e in catalog if _norm(e.get("group")) == _norm(group)]
    scored = []
    for entry in catalog:
        s = _score_entry(entry, q)
        if s > 0 or not q:
            scored.append((s, entry))
    if q:
        scored = [x for x in scored if x[0] > 0]
        scored_by_key = dict(
            (entry.get("key"), (score, entry)) for score, entry in scored
        )

        recent_block = []
        recent_keys = set()
        for recent_entry in recent_history.get_search_recent_entries():
            key = recent_entry.get("key")
            if key in recent_keys:
                continue
            scored_item = scored_by_key.get(key)
            if scored_item is None:
                continue
            score, entry = scored_item
            recent_block.append((score, _copy_entry(entry, "recent")))
            recent_keys.add(key)

        remaining = [
            (score, _copy_entry(entry, "full"))
            for score, entry in scored
            if entry.get("key") not in recent_keys
        ]
        remaining.sort(key=lambda x: _ranking_sort_key(x[0], x[1], rankings))
        scored = recent_block + remaining
    else:
        scored.sort(key=lambda x: _ranking_sort_key(x[0], x[1], rankings))

    return [e for _, e in scored[:limit]]
