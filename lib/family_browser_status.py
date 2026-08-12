# -*- coding: utf-8 -*-
"""
Family Browser status / breadcrumb / count controller.

Thin wrapper around the status labels so the dialog does not own label
updating details.
"""
import i18n


class StatusController(object):
    def __init__(self, ui):
        self.ui = ui

    def set_status(self, text):
        if self.ui is not None:
            self.ui.StatusText.Text = text

    def set_breadcrumb(self, text):
        if self.ui is not None:
            self.ui.BreadcrumbText.Text = text

    def update_count(self, shown, total=None):
        if self.ui is None:
            return
        if total is not None and total != shown:
            self.ui.CountText.Text = i18n.t("count_search", a=shown, b=total)
        else:
            self.ui.CountText.Text = i18n.t("count_items", n=shown)
