# -*- coding: utf-8 -*-
"""Map Revit UI language to AVRO ui language (`ru` | `en`)."""
from __future__ import print_function

import clr

clr.AddReference("RevitAPI")

from Autodesk.Revit.ApplicationServices import LanguageType
from pyrevit import HOST_APP


def _u(text):
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    try:
        return unicode(text)
    except Exception:
        return u""


def detect_ui_language():
    """
    Return `ru` for Russian Revit UI.
    Return `en` for English or any unknown/non-Russian Revit UI.
    """
    try:
        uiapp = HOST_APP.uiapp if HOST_APP is not None else None
        app = uiapp.Application if uiapp is not None else None
        if app is None:
            return u"en"
        language = getattr(app, "Language", None)

        try:
            if language == LanguageType.Russian:
                return u"ru"
        except Exception:
            pass

        try:
            if language in (LanguageType.English_USA, LanguageType.English_GB):
                return u"en"
        except Exception:
            pass

        text = _u(language)
        if u"Russian" in text or u"Рус" in text:
            return u"ru"
        return u"en"
    except Exception:
        return u"en"
