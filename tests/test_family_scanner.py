# -*- coding: utf-8 -*-
import builtins
import os
import tempfile
import sys
import unittest

# Python3 test shim for IronPython-oriented modules.
if not hasattr(builtins, "unicode"):
    builtins.unicode = str
if not hasattr(builtins, "basestring"):
    builtins.basestring = (str, bytes)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB = os.path.join(ROOT, "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import family_scanner  # noqa: E402


class FakeFamilyInfo(object):
    def __init__(self, name, category, folder, rel_path, revit_version):
        self.name = name
        self.category = category
        self.folder = folder
        self.rel_path = rel_path
        self.revit_version = revit_version


class FamilyScannerTests(unittest.TestCase):
    def test_scan_ignores_non_rfa_only_folders(self):
        root = tempfile.mkdtemp(prefix="avro-scan-")
        try:
            os.makedirs(os.path.join(root, "Docs", "Empty"))
            with open(os.path.join(root, "Docs", "notes.txt"), "w") as stream:
                stream.write("not a family")
            os.makedirs(os.path.join(root, "Content", "Doors"))
            path = os.path.join(root, "Content", "Doors", "Door.rfa")
            with open(path, "wb") as stream:
                stream.write(b"not a real family")
            result = family_scanner.scan_library([root])
            self.assertEqual([fi.name for fi in result["all"]], ["Door"])
            self.assertEqual(
                sorted(result["index"].keys()),
                [os.path.normpath(root),
                 os.path.normpath(os.path.join(root, "Content")),
                 os.path.normpath(os.path.join(root, "Content", "Doors"))])
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_category_from_path_under_library_root(self):
        rfa = "/lib/root/Doors/Single/Door_A.rfa"
        root = "/lib/root"
        self.assertEqual(family_scanner.category_from_path(rfa, root), "Single")

    def test_category_from_path_without_root_uses_parent(self):
        rfa = "/lib/root/Furniture/Chair_A.rfa"
        self.assertEqual(family_scanner.category_from_path(rfa), "Furniture")

    def test_flat_search_empty_query_returns_empty(self):
        rows = [FakeFamilyInfo("A", "Cat", "Folder", "Rel", "R24")]
        self.assertEqual(family_scanner.flat_search(rows, "   "), [])

    def test_flat_search_matches_family_names_and_sorts(self):
        rows = [
            FakeFamilyInfo("Window_Z", "Windows", "Facade", "A/Facade", "R25"),
            FakeFamilyInfo("Door_A", "Doors", "Core", "B/Core", "R24"),
            FakeFamilyInfo("Desk_B", "Furniture", "Office", "C/Work", "R22"),
        ]

        by_name = family_scanner.flat_search(rows, "window")
        self.assertEqual([x.name for x in by_name], ["Window_Z"])

        self.assertEqual(family_scanner.flat_search(rows, "doors"), [])
        self.assertEqual(family_scanner.flat_search(rows, "office"), [])
        self.assertEqual(family_scanner.flat_search(rows, "facade"), [])
        self.assertEqual(family_scanner.flat_search(rows, "r2"), [])


if __name__ == "__main__":
    unittest.main()
