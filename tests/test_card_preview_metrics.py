# -*- coding: utf-8 -*-
import builtins
import os
import sys
import unittest

if not hasattr(builtins, "unicode"):
    builtins.unicode = str
if not hasattr(builtins, "basestring"):
    builtins.basestring = str

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB = os.path.join(ROOT, "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

from card_layout import compute_preview_box  # noqa: E402


class PreviewBoxMetricsTests(unittest.TestCase):
    def test_keeps_base_aspect(self):
        pw, ph = compute_preview_box(156, 182, 96, 67, 24, 78)
        self.assertAlmostEqual(ph / pw, 67.0 / 96.0, places=4)

    def test_scales_with_wider_card(self):
        pw1, ph1 = compute_preview_box(156, 182, 96, 67)
        h2 = 182 * (200 / 156.0)
        pw2, ph2 = compute_preview_box(200, h2, 96, 67)
        self.assertGreater(pw2, pw1)
        self.assertGreater(ph2, ph1)
        self.assertAlmostEqual(ph2 / pw2, ph1 / pw1, places=4)

    def test_clamps_to_text_zone(self):
        pw, ph = compute_preview_box(156, 100, 96, 67, 24, 78)
        # max_ph = max(40, card_h - text_zone) => floor 40
        self.assertLessEqual(ph, 40.0 + 0.01)
        self.assertAlmostEqual(ph / pw, 67.0 / 96.0, places=3)

    def test_old_bug_would_freeze_height_at_67(self):
        h = 220 * (182 / 156.0)
        pw, ph = compute_preview_box(220, h, 96, 67)
        self.assertNotAlmostEqual(ph, 67.0, places=1)
        self.assertGreater(ph, 80.0)


if __name__ == "__main__":
    unittest.main()
