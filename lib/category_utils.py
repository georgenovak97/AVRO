# -*- coding: utf-8 -*-
"""Canonical Revit category keys and localized filter labels."""
from __future__ import print_function

import re

from revit_utils import as_unicode


_CATEGORY_ALIASES = {
    u"furniture": "furniture",
    u"мебель": "furniture",
    u"doors": "doors",
    u"двери": "doors",
    u"windows": "windows",
    u"окна": "windows",
    u"structural columns": "structural_columns",
    u"несущие колонны": "structural_columns",
    u"structural framing": "structural_framing",
    u"несущий каркас": "structural_framing",
    u"plumbing fixtures": "plumbing_fixtures",
    u"сантехнические приборы": "plumbing_fixtures",
    u"lighting fixtures": "lighting_fixtures",
    u"осветительные приборы": "lighting_fixtures",
    u"electrical fixtures": "electrical_fixtures",
    u"электрические приборы": "electrical_fixtures",
    u"mechanical equipment": "mechanical_equipment",
    u"механическое оборудование": "mechanical_equipment",
    u"air terminals": "air_terminals",
    u"воздухораспределители": "air_terminals",
    u"duct fittings": "duct_fittings",
    u"соединительные детали воздуховодов": "duct_fittings",
    u"pipe fittings": "pipe_fittings",
    u"соединительные детали трубопроводов": "pipe_fittings",
    u"specialty equipment": "specialty_equipment",
    u"специальное оборудование": "specialty_equipment",
    u"casework": "casework",
    u"встроенные элементы": "casework",
    u"parking": "parking",
    u"парковка": "parking",
    u"site": "site",
    u"генплан": "site",
    u"stairs": "stairs",
    u"лестницы": "stairs",
    u"railings": "railings",
    u"ограждения": "railings",
    u"curtain panels": "curtain_panels",
    u"панели занавеса": "curtain_panels",
    u"generic models": "generic_models",
    u"обобщенные модели": "generic_models",
}

_CATEGORY_I18N_KEYS = {
    "furniture": "category_furniture",
    "doors": "category_doors",
    "windows": "category_windows",
    "structural_columns": "category_structural_columns",
    "structural_framing": "category_structural_framing",
    "plumbing_fixtures": "category_plumbing_fixtures",
    "lighting_fixtures": "category_lighting_fixtures",
    "electrical_fixtures": "category_electrical_fixtures",
    "mechanical_equipment": "category_mechanical_equipment",
    "air_terminals": "category_air_terminals",
    "duct_fittings": "category_duct_fittings",
    "pipe_fittings": "category_pipe_fittings",
    "specialty_equipment": "category_specialty_equipment",
    "casework": "category_casework",
    "parking": "category_parking",
    "site": "category_site",
    "stairs": "category_stairs",
    "railings": "category_railings",
    "curtain_panels": "category_curtain_panels",
    "generic_models": "category_generic_models",
}


def _category_text(value):
    return re.sub(r"\s+", u" ", as_unicode(value or u"").strip().lower())


def normalize_category(value):
    """Return a stable key for known Revit category names."""
    text = _category_text(value)
    if not text:
        return u""
    return _CATEGORY_ALIASES.get(text, text)


def display_name(value, translate):
    """Return localized label for a canonical key, or the original value."""
    key = normalize_category(value)
    i18n_key = _CATEGORY_I18N_KEYS.get(key)
    if i18n_key:
        label = translate(i18n_key)
        if label != i18n_key:
            return label
    return as_unicode(value or u"").strip()
