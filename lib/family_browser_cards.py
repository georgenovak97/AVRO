# -*- coding: utf-8 -*-
"""
Family Browser card UI builders.

Builds WPF Border cards for the family grid. Kept separate from the dialog so
preview sizing, theming and event wiring can be tested / iterated without the
full FamilyBrowserDialog in memory.
"""
import System
from System.Windows import Visibility
from System.Windows.Controls import Border, StackPanel, Image, TextBlock, Grid, RowDefinition
from System.Windows.Media import Stretch
from System.Windows import (
    HorizontalAlignment,
    VerticalAlignment,
    TextWrapping,
    Thickness,
    GridLength,
    GridUnitType,
)

from revit_utils import as_unicode
import i18n
from card_layout import compute_preview_box


def make_card(fi, dialog, brushes, card_w=None, card_h=None, preview_w=None, preview_h=None):
    """Build a WPF card for one family (grid with preview)."""
    if card_w is None:
        card_w = 156.0
    if card_h is None:
        card_h = 182.0
    if preview_w is None:
        preview_w = 96.0
    if preview_h is None:
        preview_h = 67.0

    card = Border()
    card.Background = brushes["card"]
    card.BorderBrush = brushes["border"]
    card.BorderThickness = Thickness(1)
    card.CornerRadius = System.Windows.CornerRadius(3)
    card.Margin = Thickness(0)
    card.Padding = Thickness(8, 8, 8, 6)
    card.Cursor = System.Windows.Input.Cursors.Hand
    card.Width = card_w
    card.Height = card_h
    card.Tag = fi
    card.SnapsToDevicePixels = True
    try:
        card.UseLayoutRounding = True
    except Exception:
        pass

    root = Grid()
    # Row0 preview (star), Row1 text block (auto)
    rd0 = RowDefinition()
    rd0.Height = GridLength(1, GridUnitType.Star)
    rd1 = RowDefinition()
    rd1.Height = GridLength(1, GridUnitType.Auto)
    root.RowDefinitions.Add(rd0)
    root.RowDefinitions.Add(rd1)

    preview_host = Border()
    preview_host.Background = brushes.get("card") or brushes["card"]
    preview_host.BorderThickness = Thickness(0)
    preview_host.Padding = Thickness(0)
    preview_host.HorizontalAlignment = HorizontalAlignment.Stretch
    preview_host.VerticalAlignment = VerticalAlignment.Stretch
    Grid.SetRow(preview_host, 0)

    preview_img = Image()
    preview_img.Stretch = Stretch.Uniform
    preview_img.HorizontalAlignment = HorizontalAlignment.Center
    preview_img.VerticalAlignment = VerticalAlignment.Center
    preview_img.Margin = Thickness(0)
    preview_img.Visibility = Visibility.Collapsed
    preview_host.Child = preview_img

    if fi.preview is not None:
        preview_img.Source = fi.preview
        preview_img.Visibility = Visibility.Visible

    text_sp = StackPanel()
    text_sp.HorizontalAlignment = HorizontalAlignment.Stretch
    text_sp.Margin = Thickness(0, 4, 0, 0)
    Grid.SetRow(text_sp, 1)

    name_block = TextBlock()
    name_block.Text = as_unicode(fi.name)
    name_block.Foreground = brushes["text"]
    name_block.FontSize = 11
    name_block.TextWrapping = TextWrapping.Wrap
    name_block.TextAlignment = System.Windows.TextAlignment.Center
    name_block.MaxHeight = 32
    name_block.TextTrimming = System.Windows.TextTrimming.CharacterEllipsis
    try:
        name_block.LineHeight = 14
    except Exception:
        pass

    size_block = TextBlock()
    size_mb = fi.size_kb / 1024.0
    size_block.Text = i18n.t("size_mb").format(size_mb)
    size_block.Foreground = brushes["muted"]
    size_block.FontSize = 10
    size_block.HorizontalAlignment = HorizontalAlignment.Center
    size_block.Margin = Thickness(0, 2, 0, 0)

    ver_label = as_unicode(getattr(fi, "revit_version", u"") or u"")
    version_block = TextBlock()
    version_block.Text = ver_label if ver_label else u"—"
    version_block.Foreground = brushes["muted"]
    version_block.FontSize = 11
    version_block.FontWeight = System.Windows.FontWeights.SemiBold
    version_block.HorizontalAlignment = HorizontalAlignment.Center
    version_block.Margin = Thickness(0, 2, 0, 0)

    text_sp.Children.Add(name_block)
    text_sp.Children.Add(size_block)
    text_sp.Children.Add(version_block)

    root.Children.Add(preview_host)
    root.Children.Add(text_sp)
    card.Child = root

    apply_card_metrics(card, preview_img, card_w, card_h, preview_w, preview_h)

    def mouse_enter(s, e):
        if fi.path not in dialog._selected_paths:
            s.Background = brushes["hover"]

    def mouse_leave(s, e):
        if fi.path not in dialog._selected_paths:
            s.Background = brushes["card"]

    def mouse_click(s, e):
        dialog._on_card_click(s, fi, e)

    def mouse_right_click(s, e):
        dialog._on_card_right_click(s, fi, e)

    def mouse_middle_click(s, e):
        dialog._on_card_middle_click(s, fi, e)

    card.MouseEnter += mouse_enter
    card.MouseLeave += mouse_leave
    card.MouseLeftButtonDown += mouse_click
    card.MouseRightButtonDown += mouse_right_click
    card.MouseMiddleButtonDown += mouse_middle_click

    return card, preview_img


def apply_card_metrics(card, preview_img, card_w, card_h, preview_w, preview_h):
    """Size card + preview image to current adaptive cell (stable aspect)."""
    card.Width = float(card_w)
    card.Height = float(card_h)
    pw, ph = compute_preview_box(card_w, card_h, preview_w, preview_h)
    preview_img.Width = pw
    preview_img.Height = ph
    preview_img.Stretch = Stretch.Uniform
    preview_img.HorizontalAlignment = HorizontalAlignment.Center
    preview_img.VerticalAlignment = VerticalAlignment.Center
