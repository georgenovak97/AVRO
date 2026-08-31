# -*- coding: utf-8 -*-
"""Filesystem helpers for the AVRO local Markdown library."""
import codecs
import os


class FolderNode(object):
    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.folders = []
        self.files = []


def read_text(path):
    """Read common Obsidian encodings without requiring third-party modules."""
    for encoding in ("utf-8-sig", "utf-16", "cp1251", "latin-1"):
        try:
            with codecs.open(path, "r", encoding) as stream:
                return stream.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(path, "rb") as stream:
        return stream.read().decode("utf-8", "replace")


def scan_documents(root):
    root = os.path.abspath(root or "")
    node = FolderNode(os.path.basename(root) or root, root)
    if not os.path.isdir(root):
        return node, 0
    total = 0
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted([d for d in dirs if not d.startswith(".")],
                         key=lambda value: value.lower())
        relative = os.path.relpath(current, root)
        target = node
        if relative != ".":
            for part in relative.split(os.sep):
                found = [item for item in target.folders if item.name == part]
                if found:
                    target = found[0]
                else:
                    child = FolderNode(part, os.path.join(target.path, part))
                    target.folders.append(child)
                    target = child
        target.files = sorted(
            [os.path.join(current, name) for name in files
             if name.lower().endswith(".md") and not name.startswith(".")],
            key=lambda value: os.path.basename(value).lower())
        total += len(target.files)
    return node, total


def search_documents(root, query):
    """Return Markdown files whose text contains the complete query."""
    query = (query or u"").strip().lower()
    if not query:
        return []
    results = []
    for current, dirs, files in os.walk(os.path.abspath(root or "")):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if name.startswith(".") or not name.lower().endswith(".md"):
                continue
            path = os.path.join(current, name)
            try:
                text = read_text(path)
            except Exception:
                continue
            position = text.lower().find(query)
            if position < 0:
                continue
            start = max(0, position - 90)
            end = min(len(text), position + len(query) + 130)
            snippet = " ".join(text[start:end].split())
            results.append((path, snippet))
    results.sort(key=lambda item: os.path.basename(item[0]).lower())
    return results
