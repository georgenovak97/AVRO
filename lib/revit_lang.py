# -*- coding: utf-8 -*-
"""Map Revit session UI language to AVRO ui_language (ru | en)."""
from __future__ import print_function


def _revit_application():
    try:
        from pyrevit import revit
        doc = getattr(revit, "doc", None)
        if doc is not None:
            return doc.Application
    except Exception:
        pass
    try:
        return __revit__
    except Exception:
        pass
    return None


def detect_ui_language():
    """Return ``ru`` or ``en`` from Revit.Application.Language."""
    app = _revit_application()
    if app is None:
        return u"en"

    try:
        import clr
        clr.AddReference("RevitAPI")
        from Autodesk.Revit.ApplicationServices import LanguageType
    except Exception:
        return u"en"

    try:
        lt = app.Language
    except Exception:
        return u"en"

    try:
        if lt == LanguageType.Russian:
            return u"ru"
    except Exception:
        pass

    name = _as_unicode(lt).lower()
    if u"russian" in name or name.endswith(u"rus"):
        return u"ru"
    return u"en"


def _as_unicode(text):
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    try:
        return unicode(text)
    except Exception:
        return u""
