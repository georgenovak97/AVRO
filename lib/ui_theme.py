# -*- coding: utf-8 -*-
"""Light / Revit 2024 dark palettes for Family Browser WPF UI."""
from System.Windows.Media import SolidColorBrush, Color

# Dark UI: base #222836 (darkest), #3B4254 (panels), derived blues-grays
DARK = {
    "BgWindow": "#222836",
    "BgPanel": "#3B4254",
    "BgSidebar": "#222836",
    "BgToolbar": "#323A4D",
    "BgInput": "#2E3448",
    "BorderMain": "#4A5168",
    "BorderLight": "#3D4558",
    "TextMain": "#ECEFF4",
    "TextMuted": "#A8B0C0",
    "SelBg": "#3D5A80",
    "SelBorder": "#5B9BD5",
    "BtnFace": "#3B4254",
    "BtnFaceHov": "#434C5E",
    "BtnBorder": "#4C566A",
    "BtnPressed": "#2E4460",
    "BtnPrimary": "#3B4254",
    "TreeHoverBg": "#434C5E",
    "ClearBtnHover": "#434C5E",
    "ClearBtnPressed": "#4C566A",
    "Card": "#323A4D",
    "CardHover": "#434C5E",
    "CardSel": "#3D5A80",
    "CardSelBorder": "#5B9BD5",
    "CardBorder": "#4A5168",
}

LIGHT = {
    "BgWindow": "#F0F0F0",
    "BgPanel": "#FFFFFF",
    "BgSidebar": "#E4E4E4",
    "BgToolbar": "#F5F5F5",
    "BgInput": "#FFFFFF",
    "BorderMain": "#ABABAB",
    "BorderLight": "#D0D0D0",
    "TextMain": "#1E1E1E",
    "TextMuted": "#5A5A5A",
    "SelBg": "#CCE8FF",
    "SelBorder": "#3399FF",
    "BtnFace": "#E1E1E1",
    "BtnFaceHov": "#CCE4F7",
    "BtnBorder": "#707070",
    "BtnPressed": "#B9D7F5",
    "BtnPrimary": "#E1E1E1",
    "TreeHoverBg": "#EDEDED",
    "ClearBtnHover": "#E8E8E8",
    "ClearBtnPressed": "#D0D0D0",
    "Card": "#FFFFFF",
    "CardHover": "#E8F4FC",
    "CardSel": "#CCE8FF",
    "CardSelBorder": "#3399FF",
    "CardBorder": "#ABABAB",
}

_RESOURCE_KEYS = (
    "BgWindow", "BgPanel", "BgSidebar", "BgToolbar", "BgInput",
    "BorderMain", "BorderLight", "TextMain", "TextMuted",
    "SelBg", "SelBorder", "BtnFace", "BtnFaceHov", "BtnBorder",
    "BtnPressed", "BtnPrimary", "TreeHoverBg",
    "ClearBtnHover", "ClearBtnPressed",
)


def _parse_hex(hex_str):
    h = hex_str.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError(hex_str)
    return (
        int(h[0:2], 16),
        int(h[2:4], 16),
        int(h[4:6], 16),
    )


def brush_from_hex(hex_str):
    r, g, b = _parse_hex(hex_str)
    br = SolidColorBrush(Color.FromRgb(r, g, b))
    return br


def apply_window_theme(window, palette):
    """Replace DynamicResource brushes on the window."""
    res = window.Resources
    for key in _RESOURCE_KEYS:
        if key in palette:
            res[key] = brush_from_hex(palette[key])
    if "BgWindow" in palette:
        window.Background = brush_from_hex(palette["BgWindow"])


def card_brushes(palette):
    """Brushes for family cards (script globals)."""
    return {
        "card": brush_from_hex(palette["Card"]),
        "hover": brush_from_hex(palette["CardHover"]),
        "sel": brush_from_hex(palette["CardSel"]),
        "sel_border": brush_from_hex(palette["CardSelBorder"]),
        "border": brush_from_hex(palette["CardBorder"]),
        "text": brush_from_hex(palette["TextMain"]),
        "muted": brush_from_hex(palette["TextMuted"]),
    }
