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


def element_id_value(element_id):
    """
    Return an int for an ElementId across Revit versions.

    Revit 2024+ deprecated ``ElementId.IntegerValue`` in favour of ``.Value``.
    Prefer ``.Value`` and fall back to ``IntegerValue`` for Revit 2020-2023.
    """
    if element_id is None:
        return 0
    try:
        value = getattr(element_id, "Value", None)
        if value is not None:
            return int(value)
    except Exception:
        pass
    try:
        return int(getattr(element_id, "IntegerValue"))
    except Exception:
        return 0


def instance_symbol(instance):
    """
    Return a FamilyInstance's FamilySymbol across Revit versions.

    Revit 2024+ replaced ``FamilyInstance.Symbol`` with ``GetFamilySymbol()``.
    Prefer the method and fall back to the property for Revit 2020-2023.
    """
    if instance is None:
        return None
    getter = getattr(instance, "GetFamilySymbol", None)
    if callable(getter):
        try:
            symbol = getter()
            if symbol is not None:
                return symbol
        except Exception:
            pass
    try:
        return getattr(instance, "Symbol", None)
    except Exception:
        return None
