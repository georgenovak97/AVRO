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
from System.Windows.Controls import Border, TextBlock, StackPanel

import family_inspector
import i18n
import avro_log
from revit_utils import as_unicode

try:
    basestring
except NameError:  # python3 test environment
    basestring = (str, bytes)


def _yield_ui():
    """Pump WPF render/layout messages so UI updates before blocking operation."""
    try:
        from System.Windows.Threading import (
            Dispatcher, DispatcherFrame, DispatcherPriority)
        import System
        frame = DispatcherFrame()

        def exit_frame():
            frame.Continue = False

        app = System.Windows.Application.Current
        disp = app.Dispatcher if app is not None else Dispatcher.CurrentDispatcher
        if disp is not None:
            disp.BeginInvoke(
                DispatcherPriority.Background,
                System.Action(exit_frame))
            Dispatcher.PushFrame(frame)
    except Exception:
        pass


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
        meta = family_inspector.load_cached(path)
        if meta is None:
            self.set_loading(path)
            _yield_ui()
            if self._props_path != path:
                return
            try:
                app = self.dialog.doc.Application if self.dialog.doc is not None else None
            except Exception as ex:
                avro_log.exception("props.inspect.app", ex)
                app = None
            meta = family_inspector.inspect(path, app=app, use_cache=True)
        else:
            self._props_path = path
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
        shared = meta.get("shared_nested")
        shared = [] if shared is None else (shared or [])
        has_shared = meta.get("has_shared_nested")
        if has_shared is None and meta.get("shared_nested") is not None:
            has_shared = bool(shared)

        rows = (
            (i18n.t("props_version"), ver),
            (i18n.t("props_category"), meta.get("category") or getattr(fi, "category", u"")),
            (i18n.t("props_name"), getattr(fi, "name", u"")),
            (i18n.t("props_size"), i18n.t("size_mb").format(size_mb)),
            (i18n.t("props_modified"), getattr(fi, "modified", u"")),
        )
        for label, value in rows:
            panel.Children.Add(self._row(label, value))

        self._render_separator(panel)
        self._render_list(panel, i18n.t("props_types"), meta.get("types") or [])
        self._render_list(
            panel, i18n.t("props_shared_nested"), shared,
            empty_text=i18n.t("props_no"))
        panel.Children.Add(self._row(
            i18n.t("props_shared_family"),
            self._yes_no(meta.get("is_shared_family"))))
        panel.Children.Add(self._row(
            i18n.t("props_has_nested"), self._yes_no(has_shared)))

        self._render_separator(panel)
        rows = (
            (i18n.t("props_hosting"), self.dialog._host_label(meta.get("hosting"))),
            (i18n.t("props_placement"), meta.get("placement") or u""),
            (i18n.t("props_work_plane_based"), self._yes_no(meta.get("work_plane_based"))),
            (i18n.t("props_imported"), self._yes_no(meta.get("has_imported_geometry"))),
        )
        for label, value in rows:
            panel.Children.Add(self._row(label, value))

        self._render_separator(panel)
        rows = (
            (i18n.t("props_params"), u"{} (inst {}, type {})".format(
                meta.get("param_total_count") or 0,
                meta.get("param_instance_count") or 0,
                meta.get("param_type_count") or 0)),
            (i18n.t("props_dimensions"), self._count(meta, "dimension_count")),
            (i18n.t("props_params_formulas"), self._yes_no(meta.get("param_has_formulas"))),
            (i18n.t("props_materials"), self._count(meta, "material_count")),
        )
        for label, value in rows:
            panel.Children.Add(self._row(label, value))

        # Attach hosting/placement on FamilyInfo for subsequent filters.
        try:
            fi.hosting = meta.get("hosting") or family_inspector.HOST_UNKNOWN
            fi.placement = as_unicode(meta.get("placement") or u"")
        except Exception as ex:
            avro_log.exception("props.fill.attach-meta", ex)
        # Refresh filter option lists so new category/placement appear
        if self.rebuild_filters_callback is not None:
            try:
                self.rebuild_filters_callback(preserve=True)
            except Exception as ex:
                avro_log.exception("props.fill.rebuild-filters", ex)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _count(self, meta, key):
        value = meta.get(key)
        return i18n.t("props_unknown") if value is None else as_unicode(value)

    def _yes_no(self, flag):
        # tri-state: yes / no / unknown
        if isinstance(flag, basestring):
            key = as_unicode(flag).strip().lower()
            if key in (u"yes", u"true", u"1"):
                return i18n.t("props_yes")
            if key in (u"no", u"false", u"0"):
                return i18n.t("props_no")
            return i18n.t("props_unknown")
        if flag is None:
            return i18n.t("props_unknown")
        return i18n.t("props_yes") if bool(flag) else i18n.t("props_no")

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

    def _render_separator(self, panel):
        separator = Border()
        separator.Height = 1
        separator.Background = self.brushes["border"]
        separator.Opacity = 0.3
        separator.Margin = Thickness(0, 7, 0, 7)
        panel.Children.Add(separator)

    def _render_list(self, panel, title, items, empty_text=None):
        title_block = TextBlock()
        title_block.Text = as_unicode(title)
        title_block.FontSize = 11
        title_block.Foreground = self.brushes["muted"]
        title_block.Margin = Thickness(0, 6, 0, 4)
        panel.Children.Add(title_block)
        if not items:
            panel.Children.Add(self._row(
                u"", empty_text or i18n.t("props_none"), muted=True))
        else:
            for name in items:
                tb = TextBlock()
                tb.Text = u"• " + as_unicode(name)
                tb.TextWrapping = TextWrapping.Wrap
                tb.FontSize = 12
                tb.Foreground = self.brushes["text"]
                tb.Margin = Thickness(0, 0, 0, 3)
                panel.Children.Add(tb)
