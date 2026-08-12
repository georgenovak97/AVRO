# -*- coding: utf-8 -*-
"""
IFamilyLoadOptions implementation used when loading families into a project.

Extracted so the dialog script does not mix Revit API boilerplate with UI code.
"""
import clr
clr.AddReference("RevitAPI")

import Autodesk.Revit.DB as RDB
from Autodesk.Revit.DB import IFamilyLoadOptions


class FamilyLoadOptions(IFamilyLoadOptions):
    """Allow reload/overwrite when the family is already in the project."""

    @staticmethod
    def _set_out_bool(out_param, value):
        try:
            out_param.Value = value
        except Exception:
            try:
                out_param[0] = value
            except Exception:
                pass

    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        self._set_out_bool(overwriteParameterValues, True)
        return True

    def OnSharedFamilyFound(
            self, sharedFamily, familyInUse, source, overwriteParameterValues):
        self._set_out_bool(overwriteParameterValues, True)
        try:
            source.Value = RDB.FamilySource(0)
        except Exception:
            try:
                source[0] = RDB.FamilySource(0)
            except Exception:
                pass
        return True


FAMILY_LOAD_OPTIONS = FamilyLoadOptions()
