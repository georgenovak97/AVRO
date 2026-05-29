# -*- coding: utf-8 -*-
"""Current Search profile: Revit version + Revit UI language."""
from __future__ import print_function

import os

import clr

clr.AddReference("RevitAPI")

from Autodesk.Revit.ApplicationServices import LanguageType
from pyrevit import HOST_APP

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KEYS_DIR = os.path.join(_ROOT, "keys")


def _u(text):
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    try:
        return unicode(text)
    except Exception:
        return unicode(str(text), "utf-8", "ignore")


def _version_number():
    try:
        uiapp = HOST_APP.uiapp if HOST_APP is not None else None
        app = uiapp.Application if uiapp is not None else None
        if app is None:
            return u""
        return _u(getattr(app, "VersionNumber", u""))
    except Exception:
        return u""


def get_version_tag():
    version = _version_number().strip()
    digits = u"".join(ch for ch in version if ch.isdigit())
    if len(digits) >= 2:
        return u"R" + digits[-2:]
    return u"R00"


def get_language_tag():
    try:
        uiapp = HOST_APP.uiapp if HOST_APP is not None else None
        app = uiapp.Application if uiapp is not None else None
        if app is None:
            return u"ENU"
        language = getattr(app, "Language", None)

        try:
            if language == LanguageType.Russian:
                return u"RUS"
        except Exception:
            pass

        try:
            if language in (LanguageType.English_USA, LanguageType.English_GB):
                return u"ENU"
        except Exception:
            pass

        text = _u(language)
        if u"Russian" in text or u"Рус" in text:
            return u"RUS"
        return u"ENU"
    except Exception:
        return u"ENU"


def get_profile_key():
    return u"{}_{}".format(get_version_tag(), get_language_tag())


def _parse_version_number(version_tag):
    digits = u"".join(ch for ch in _u(version_tag) if ch.isdigit())
    try:
        return int(digits or 0)
    except Exception:
        return 0


def _available_profiles(language_tag):
    base_dir = os.path.join(_KEYS_DIR, language_tag)
    out = []
    if not os.path.isdir(base_dir):
        return out
    try:
        for name in os.listdir(base_dir):
            xml_path = os.path.join(base_dir, name, "KeyboardShortcuts.xml")
            if not os.path.isfile(xml_path):
                continue
            out.append({
                "profile_key": _u(name),
                "xml_path": xml_path,
                "version_tag": _u(name).split(u"_", 1)[0],
                "language_tag": language_tag,
            })
    except Exception:
        return []
    out.sort(key=lambda x: _parse_version_number(x.get("version_tag")))
    return out


def _resolve_profile(version_tag, language_tag):
    profile_key = u"{}_{}".format(version_tag, language_tag)
    xml_path = os.path.join(_KEYS_DIR, language_tag, profile_key, "KeyboardShortcuts.xml")
    if os.path.isfile(xml_path):
        return {
            "profile_key": profile_key,
            "xml_path": xml_path,
            "version_tag": version_tag,
            "language_tag": language_tag,
            "xml_exists": True,
            "fallback_used": False,
        }

    available = _available_profiles(language_tag)
    if not available and language_tag != u"ENU":
        available = _available_profiles(u"ENU")
        language_tag = u"ENU"
    if not available:
        return {
            "profile_key": profile_key,
            "xml_path": xml_path,
            "version_tag": version_tag,
            "language_tag": language_tag,
            "xml_exists": False,
            "fallback_used": False,
        }

    requested_v = _parse_version_number(version_tag)
    candidates = [
        item for item in available
        if _parse_version_number(item.get("version_tag")) <= requested_v
    ]
    chosen = candidates[-1] if candidates else available[-1]
    return {
        "profile_key": chosen.get("profile_key"),
        "xml_path": chosen.get("xml_path"),
        "version_tag": chosen.get("version_tag"),
        "language_tag": chosen.get("language_tag"),
        "xml_exists": True,
        "fallback_used": chosen.get("profile_key") != profile_key,
    }


def get_profile_info():
    requested_version_tag = get_version_tag()
    requested_language_tag = get_language_tag()
    resolved = _resolve_profile(requested_version_tag, requested_language_tag)
    resolved["requested_version_tag"] = requested_version_tag
    resolved["requested_language_tag"] = requested_language_tag
    resolved["requested_profile_key"] = u"{}_{}".format(
        requested_version_tag, requested_language_tag)
    return resolved


def is_project_document_active():
    """True when Search may run: open project document, not family editor."""
    try:
        uiapp = HOST_APP.uiapp if HOST_APP is not None else None
        if uiapp is None:
            return False
        uidoc = uiapp.ActiveUIDocument
        if uidoc is None:
            return False
        doc = uidoc.Document
        if doc is None:
            return False
        return not bool(getattr(doc, "IsFamilyDocument", False))
    except Exception:
        return False


def iter_version_profile_infos():
    info = get_profile_info()
    return [info] if info.get("xml_exists") else []
