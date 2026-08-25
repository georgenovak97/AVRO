# -*- coding: utf-8 -*-
import os
import tempfile
import unittest

import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB = os.path.join(ROOT, "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import rfa_version  # noqa: E402


class RfaVersionTests(unittest.TestCase):
    def _version_from_bytes(self, text, encoding="utf-16-le"):
        fd, path = tempfile.mkstemp(suffix=".rfa")
        os.close(fd)
        try:
            with open(path, "wb") as stream:
                stream.write(text.encode(encoding))
            return rfa_version.revit_version_label(path)
        finally:
            os.remove(path)

    def test_detects_utf16_legacy_format(self):
        self.assertEqual(
            self._version_from_bytes("Autodesk Revit 2019"), "R19")

    def test_detects_utf16_modern_format(self):
        self.assertEqual(self._version_from_bytes("2024\x12Build"), "R24")

    def test_path_version_remains_fast_fallback(self):
        self.assertEqual(
            rfa_version.revit_version_label("/library/R23/Doors/Door.rfa"),
            "R23")


if __name__ == "__main__":
    unittest.main()
