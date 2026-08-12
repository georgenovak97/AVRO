# -*- coding: utf-8 -*-
"""
Common Revit / IronPython helpers used across AVRO extension.

These utilities isolate IronPython quirks from business logic:
- Unicode handling under IronPython 2.7
- Reading Element.Name when the name is shadowed by imports
- Accessing FamilySymbol.Family under the same shadowing issue
"""


def as_unicode(text):
    """Return a unicode string; IronPython 2.7 safe."""
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    try:
        return unicode(text)
    except Exception:
        return u""


def revit_name(element):
    """
    Read Element.Name under IronPython.

    Importing ``Family`` or ``FamilySymbol`` shadows ``element.Name``
    (NameError: Name). Use the descriptor directly as a fallback.
    """
    if element is None:
        return u""
    from Autodesk.Revit.DB import Element
    try:
        return as_unicode(Element.Name.__get__(element, type(element)))
    except Exception:
        pass
    try:
        return as_unicode(getattr(element, "Name"))
    except Exception:
        return u""


def symbol_family(symbol):
    """FamilySymbol.Family — same IronPython shadowing as Element.Name."""
    if symbol is None:
        return None
    try:
        return getattr(symbol, "Family")
    except Exception:
        return None
