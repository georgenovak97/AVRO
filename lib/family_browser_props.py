# -*- coding: utf-8 -*-
"""
Family Browser properties panel controller.

Renders family metadata (category, hosting, placement, types, parameters)
in the right-side properties panel and triggers background inspection.
"""
import clr
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows import Thickness, Visibility, TextWrapping, FontStyles
from System.Windows.Controls import TextBlock, StackPanel
from System.Windows.Media import SolidColorBrush

import family_inspector
import i18n
from revit_utils import as_unicode


class PropsPanelController(object):
    """Manage the properties panel of the Family Browser dialog."""

    def __init__(self, dialog, brushes, rebuild_filters_callback=None):
        self.dialog = dialog
        self.brushes = brushes
        self.rebuild_filters_callback = rebuild_filters_callback
        self._props_path = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def reset(self, hint_text=None):
        """Clear the panel and show the default or custom hint."""
        panel = self.dialog.ui.PropsPanel
        hint = self.dialog.ui.PropsHint
        panel.Children.Clear()
        hint.Text = hint_text if hint_text is not None else i18n.t("props_hint")
        hint.Visibility = Visibility.Visible
        self._props_path = None

    def set_loading(self, path):
        """Show the loading state for the given family path."""
        self._props_path = path
        panel = self.dialog.ui.PropsPanel
        hint = self.dialog.ui.PropsHint
        panel.Children.Clear()
        hint.Text = i18n.t("props_loading")
        hint.Visibility = Visibility.Visible

    def inspect(self, fi):
        """Inspect *fi* and render its metadata in the panel."""
        if fi is None or not getattr(fi, "path", None):
            self.reset()
            return
        path = fi.path
        self.set_loading(path)
        meta = family_inspector.load_cached(path)
        if meta is None:
            try:
                app = self.dialog.doc.Application if self.dialog.doc is not None else None
            except Exception:
                app = None
            meta = family_inspector.inspect(path, app=app, use_cache=True)
        if self._props_path != path:
            return
        self.fill(fi, meta)

    def fill(self, fi, meta):
        """Render metadata into the panel."""
        panel = self.dialog.ui.PropsPanel
        hint = self.dialog.ui.PropsHint
        panel.Children.Clear()
        if not meta or not meta.get("ok"):
            err = as_unicode((meta or {}).get("error") or u"error")
            hint.Text = i18n.t("props_error", err=err)
            hint.Visibility = Visibility.Visible
            return
        hint.Visibility = Visibility.Collapsed

        size_mb = (fi.size_kb / 1024.0) if fi else 0.0
        ver = as_unicode(
            meta.get("revit_format")
            or getattr(fi, "revit_version", u"")
            or u"")
        shared = meta.get("shared_nested") or []
        shared_text = (
            u", ".join([as_unicode(x) for x in shared])
            if shared else self._yes_no(False))
        if shared:
            shared_text = u"{} ({})".format(self._yes_no(True), shared_text)

        rows = (
            (i18n.t("props_name"), getattr(fi, "name", u"")),
            (i18n.t("props_category"), meta.get("category") or getattr(fi, "category", u"")),
            (i18n.t("props_hosting"), self.dialog._host_label(meta.get("hosting"))),
            (i18n.t("props_placement"), self.dialog._placement_label(meta.get("placement"))),
            (i18n.t("props_version"), ver),
            (i18n.t("props_size"), i18n.t("size_mb").format(size_mb)),
            (i18n.t("props_imported"), self._yes_no(meta.get("has_imported_geometry"))),
            (i18n.t("props_shared_nested"), shared_text),
            (i18n.t("props_shared_family"), self._yes_no(meta.get("is_shared_family"))),
            (i18n.t("props_params"), u"{} (inst {}, type {})".format(
                meta.get("param_total_count") or 0,
                meta.get("param_instance_count") or 0,
                meta.get("param_type_count") or 0)),
            (i18n.t("props_params_formulas"), self._yes_no(meta.get("param_has_formulas"))),
        )
        for label, value in rows:
            panel.Children.Add(self._row(label, value))

        self._render_types(panel, meta.get("types") or [])

        # Attach hosting/placement on FamilyInfo for subsequent filters.
        try:
            fi.hosting = meta.get("hosting") or family_inspector.HOST_UNKNOWN
            fi.placement = as_unicode(meta.get("placement") or u"")
        except Exception:
            pass
        # Refresh filter option lists so new category/placement appear
        if self.rebuild_filters_callback is not None:
            try:
                self.rebuild_filters_callback(preserve=True)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _yes_no(self, flag):
        return i18n.t("props_yes") if flag else i18n.t("props_no")

    def _row(self, label, value, muted=False):
        tb_label = TextBlock()
        tb_label.Text = as_unicode(label)
        tb_label.FontSize = 10
        tb_label.Foreground = self.brushes["muted"]
        tb_label.Margin = Thickness(0, 4, 0, 0)

        tb_value = TextBlock()
        tb_value.Text = as_unicode(value) if value else i18n.t("props_none")
        tb_value.FontSize = 11
        tb_value.TextWrapping = TextWrapping.Wrap
        tb_value.Foreground = self.brushes["text"]
        if muted:
            tb_value.FontStyle = FontStyles.Italic

        sp = StackPanel()
        sp.Children.Add(tb_label)
        sp.Children.Add(tb_value)
        return sp

    def _render_types(self, panel, types):
        types_title = TextBlock()
        types_title.Text = u"{} ({})".format(i18n.t("props_types"), len(types))
        types_title.FontSize = 11
        types_title.Foreground = self.brushes["muted"]
        types_title.Margin = Thickness(0, 6, 0, 4)
        panel.Children.Add(types_title)
        if not types:
            panel.Children.Add(self._row(u"", i18n.t("props_none"), muted=True))
        else:
            for tname in types:
                tb = TextBlock()
                tb.Text = u"• " + as_unicode(tname)
                tb.TextWrapping = TextWrapping.Wrap
                tb.FontSize = 12
                tb.Foreground = self.brushes["text"]
                tb.Margin = Thickness(0, 0, 0, 3)
                panel.Children.Add(tb)
