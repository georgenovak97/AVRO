# -*- coding: utf-8 -*-
"""Markdown heading extraction for the Help panel."""
import re


def extract_headings(text):
    result = []
    in_fence = False
    for line in (text or "").splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            title = re.sub(r"[*_`~]", "", match.group(2)).strip()
            if title:
                result.append((len(match.group(1)), title))
    return result
