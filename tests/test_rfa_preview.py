# -*- coding: utf-8 -*-
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB = os.path.join(ROOT, "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import rfa_preview  # noqa: E402


class RfaPreviewTests(unittest.TestCase):
    def test_png_extraction_does_not_repeat_signature_scan(self):
        original = rfa_preview._find_png_in_buffer

        def fail(_data):
            raise AssertionError("redundant byte scan was called")

        rfa_preview._find_png_in_buffer = fail
        try:
            self.assertIsNone(rfa_preview._extract_png_from_bytes("no image"))
        finally:
            rfa_preview._find_png_in_buffer = original


if __name__ == "__main__":
    unittest.main()
