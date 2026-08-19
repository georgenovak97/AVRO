# -*- coding: utf-8 -*-
import builtins
import os
import sys
import unittest

if not hasattr(builtins, "unicode"):
    builtins.unicode = str

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB = os.path.join(ROOT, "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import category_utils  # noqa: E402
import family_inspector  # noqa: E402


class CategoryUtilsTests(unittest.TestCase):
    def test_english_and_russian_names_share_key(self):
        self.assertEqual(
            category_utils.normalize_category("Doors"),
            category_utils.normalize_category(u"Двери"))
        self.assertEqual(category_utils.normalize_category("Doors"), "doors")

    def test_unknown_category_is_stable(self):
        self.assertEqual(
            category_utils.normalize_category("Custom Category"),
            "custom category")

    def test_display_uses_translator_for_known_category(self):
        def translate(key):
            return {"category_doors": u"Двери"}.get(key, key)

        self.assertEqual(
            category_utils.display_name("Doors", translate), u"Двери")

    def test_cached_work_plane_hosting_has_stable_key(self):
        self.assertEqual(
            family_inspector.hosting_of(
                "x.rfa",
                cached_meta={
                    "ok": True,
                    "hosting": family_inspector.HOST_INDEPENDENT,
                    "work_plane_based": True,
                }),
            family_inspector.HOST_WORK_PLANE)


if __name__ == "__main__":
    unittest.main()
