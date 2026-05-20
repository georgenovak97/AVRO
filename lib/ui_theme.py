# -*- coding: utf-8 -*-
"""Light / Revit 2024 dark palettes for Family Manager WPF UI."""
from System.Windows.Media import SolidColorBrush, Color

# Revit 2024 dark UI (ribbon, panels, browser)
DARK = {
    "BgWindow": "#2B2D39",
    "BgPanel": "#333337",
    "BgSidebar": "#2B2B2B",
    "BgToolbar": "#3F3F46",
    "BgInput": "#3C3C3C",
    "BorderMain": "#5A5A5A",
    "BorderLight": "#464647",
    "TextMain": "#F1F1F1",
    "TextMuted": "#9D9D9D",
    "SelBg": "#264F78",
    "SelBorder": "#007ACC",
    "BtnFace": "#454545",
    "BtnFaceHov": "#5A5A5A",
    "BtnBorder": "#6E6E6E",
    "BtnPressed": "#094771",
    "BtnPrimary": "#454545",
    "TreeHoverBg": "#3E3E42",
    "ClearBtnHover": "#505050",
    "ClearBtnPressed": "#606060",
    "Card": "#3C3C3C",
    "CardHover": "#454952",
    "CardSel": "#264F78",
    "CardSelBorder": "#007ACC",
    "CardBorder": "#5A5A5A",
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
