# -*- coding: utf-8 -*-
"""
Family Browser library management controller.

Handles picking the library folder and explicit reload.
"""
import os
from System.Windows.Forms import FolderBrowserDialog, DialogResult, NativeWindow
from System.Windows.Interop import WindowInteropHelper
import i18n
import config


class LibraryController(object):
    def __init__(self, dialog):
        self.dialog = dialog

    def on_settings(self, sender, e):
        dlg = FolderBrowserDialog()
        dlg.Description = i18n.t("library_dialog_desc")
        current = self.dialog._library_path()
        if current and os.path.isdir(current):
            dlg.SelectedPath = current
        owner = NativeWindow()
        result = DialogResult.Cancel
        try:
            handle = WindowInteropHelper(self.dialog.win).Handle
            if handle:
                owner.AssignHandle(handle)
            result = dlg.ShowDialog(owner)
        finally:
            owner.ReleaseHandle()
        self.dialog._restore_window_focus()
        if result == DialogResult.OK:
            config.set_library_path(dlg.SelectedPath)
            config.clear_recent()
            self.dialog.cfg = config.load()
            self.dialog._preview_mem = {}
            self.dialog._preview_miss = set()
            self.dialog._preview_gen += 1
            self.dialog._show_catalog_after_scan = True
            self.dialog._schedule_scan()

    def on_reload(self, sender, e):
        if not self.dialog._library_path():
            self.dialog._set_status(i18n.t("library_path_required"))
            return
        config.clear_recent()
        self.dialog.cfg = config.load()
        self.dialog._preview_mem = {}
        self.dialog._preview_miss = set()
        self.dialog._preview_gen += 1
        self.dialog._card_build_gen += 1
        self.dialog._show_catalog_after_scan = True
        self.dialog._scan = {"roots": [], "all": [], "index": {}}
        self.dialog._folder_scope = []
        self.dialog._folder_scope_label = u""
        self.dialog._scope_is_recent = False
        if self.dialog.ui is not None:
            self.dialog._build_tree(self.dialog._scan)
        self.dialog._set_status(i18n.t("scanning"))
        self.dialog._schedule_scan()
