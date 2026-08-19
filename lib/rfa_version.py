# -*- coding: utf-8 -*-
"""
Detect Revit release label (R22, R24, …) from an .rfa file.
"""
import re

_RE_YEAR = re.compile(
    r"Autodesk Revit\s+(\d{4})|Revit\s+(\d{4})|Format:\s*(\d{4})",
    re.I,
)

_READ_CHUNK = 512 * 1024


def year_to_label(year):
    """Map release year 2022 -> R22, 2019 -> R19."""
    try:
        y = int(year)
    except Exception:
        return u""
    if y >= 2000:
        return u"R{:02d}".format(y % 100)
    if y >= 8:
        return u"R{}".format(y)
    return u""


def _label_from_format_string(text):
    if not text:
        return u""
    if isinstance(text, str):
        try:
            text = text.decode("utf-8", "ignore")
        except Exception:
            text = unicode(text)
    m = re.search(r"(\d{4})", text)
    if m:
        return year_to_label(m.group(1))
    m = re.search(r"\bR?(\d{2})\b", text, re.I)
    if m:
        return u"R{:02d}".format(int(m.group(1)))
    return u""


def _label_via_file_bytes(path):
    try:
        with open(path, "rb") as f:
            data = f.read(_READ_CHUNK)
    except Exception:
        return u""
    try:
        text = data.decode("latin-1")
    except Exception:
        try:
            text = unicode(data, "latin-1", "ignore")
        except Exception:
            return u""
    m = _RE_YEAR.search(text)
    if not m:
        return u""
    year = m.group(1) or m.group(2) or m.group(3)
    if year:
        return year_to_label(year)
    return u""


def revit_version_from_path(rfa_path):
    """Short label from folder names (R24, R22, …) — safe during library scan."""
    if not rfa_path:
        return u""
    norm = rfa_path.replace("\\", "/")
    for part in norm.split("/"):
        if not part:
            continue
        m = re.match(r"^R(\d{2})$", part, re.I)
        if m:
            return u"R{:02d}".format(int(m.group(1)))
    return u""


def revit_version_label(rfa_path):
    """Return display label like R22, or empty string if unknown (pure Python, no Revit API)."""
    if not rfa_path or not rfa_path.lower().endswith(".rfa"):
        return u""
    label = revit_version_from_path(rfa_path)
    if label:
        return label
    return _label_via_file_bytes(rfa_path)
