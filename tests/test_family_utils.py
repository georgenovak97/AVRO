# -*- coding: utf-8 -*-
import builtins
import os
import sys
import unittest

# Python3 test shim for IronPython-oriented modules.
if not hasattr(builtins, "unicode"):
    builtins.unicode = str

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB = os.path.join(ROOT, "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import family_utils  # noqa: E402


class FakeFamilyInfo(object):
    def __init__(self, name, path):
        self.name = name
        self.path = path


class FamilyUtilsTests(unittest.TestCase):
    def test_normalize_family_key_basic(self):
        self.assertEqual(
            family_utils.normalize_family_key(u"Door__Single Panel"),
            u"door_singlepanel",
        )

    def test_normalize_family_key_none(self):
        self.assertEqual(family_utils.normalize_family_key(None), u"")

    def test_family_name_candidates_from_name_and_stem(self):
        fi = FakeFamilyInfo(
            name=u"Desk__Type_A",
            path=u"/tmp/lib/Furniture/Desk__Type_A.rfa",
        )
        names = family_utils.family_name_candidates(fi)
        self.assertIn(u"Desk__Type_A", names)
        self.assertIn(u"Desk_Type_A", names)
        self.assertIn(u"Desk  Type A", names)
        self.assertIn(u"Desk_Type_A", names)

    def test_family_name_candidates_without_path(self):
        fi = FakeFamilyInfo(name=u"Chair_A", path=u"")
        names = family_utils.family_name_candidates(fi)
        self.assertIn(u"Chair_A", names)
        self.assertIn(u"Chair A", names)


if __name__ == "__main__":
    unittest.main()
