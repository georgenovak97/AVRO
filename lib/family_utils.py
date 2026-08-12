# -*- coding: utf-8 -*-
"""
Pure helpers for working with Revit family files and names.

No UI / WPF dependencies. Safe to import from scanner, cache, or dialog code.
"""
import os

from revit_utils import as_unicode


def normalize_family_key(name):
    """Normalize a family name for case-insensitive comparison."""
    if not name:
        return u""
    key = as_unicode(name).lower().replace(u" ", u"")
    key = key.replace(u"__", u"_")
    return key


def family_name_candidates(fi):
    """
    Possible Revit family names for a library file.

    Collects candidates from the file name, the file stem, and
    ``BasicFileInfo.Extract`` when available.
    """
    names = set()
    base = as_unicode(fi.name)
    if base:
        names.add(base)
        names.add(base.replace(u"__", u"_"))
        names.add(base.replace(u"_", u" "))
    path = getattr(fi, "path", u"") or u""
    if path:
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem:
            names.add(stem)
            names.add(stem.replace(u"__", u"_"))
    try:
        from Autodesk.Revit.DB import BasicFileInfo
        bfi = BasicFileInfo.Extract(path)
        fn = getattr(bfi, "GetFamilyName", None)
        if callable(fn):
            try:
                v = as_unicode(fn())
                if v:
                    names.add(v)
            except Exception:
                pass
    except Exception:
        pass
    return names
