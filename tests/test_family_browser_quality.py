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

import family_browser_quality as q  # noqa: E402


class Dummy(object):
    def __init__(self, path="a.rfa", size_kb=100.0):
        self.path = path
        self.size_kb = size_kb


def _flags(**kwargs):
    base = {
        "work_plane_only": False,
        "shared_only": False,
        "no_imported_cad": False,
        "limit_types": False,
        "limit_ref_planes": False,
        "limit_dimensions": False,
        "limit_nested": False,
        "limit_params": False,
        "limit_formulas": False,
        "limit_materials": False,
        "not_huge": False,
    }
    base.update(kwargs)
    return base


class QualityStrictUnknownTests(unittest.TestCase):
    def test_no_flags_always_pass(self):
        self.assertTrue(q.passes_quality_flags(Dummy(), None, _flags()))

    def test_limit_types_unknown_meta_fails(self):
        self.assertFalse(
            q.passes_quality_flags(Dummy(), None, _flags(limit_types=True))
        )
        self.assertFalse(
            q.passes_quality_flags(
                Dummy(), {"ok": False, "type_count": 1}, _flags(limit_types=True)
            )
        )

    def test_limit_types_pass_and_fail_with_meta(self):
        ok_meta = {"ok": True, "type_count": 3}
        fat_meta = {"ok": True, "type_count": 25}
        self.assertTrue(
            q.passes_quality_flags(Dummy(), ok_meta, _flags(limit_types=True))
        )
        self.assertFalse(
            q.passes_quality_flags(Dummy(), fat_meta, _flags(limit_types=True))
        )

    def test_shared_only_unknown_fails(self):
        self.assertFalse(
            q.passes_quality_flags(Dummy(), None, _flags(shared_only=True))
        )

    def test_shared_only_yes_no(self):
        self.assertTrue(
            q.passes_quality_flags(
                Dummy(),
                {"ok": True, "is_shared_family": True},
                _flags(shared_only=True),
            )
        )
        self.assertFalse(
            q.passes_quality_flags(
                Dummy(),
                {"ok": True, "is_shared_family": False},
                _flags(shared_only=True),
            )
        )

    def test_work_plane_only_unknown_and_values(self):
        self.assertFalse(
            q.passes_quality_flags(Dummy(), None, _flags(work_plane_only=True))
        )
        self.assertFalse(
            q.passes_quality_flags(
                Dummy(),
                {"ok": True, "work_plane_based": False},
                _flags(work_plane_only=True),
            )
        )
        self.assertTrue(
            q.passes_quality_flags(
                Dummy(),
                {"ok": True, "work_plane_based": True},
                _flags(work_plane_only=True),
            )
        )

    def test_no_imported_cad_unknown_and_values(self):
        self.assertFalse(
            q.passes_quality_flags(Dummy(), None, _flags(no_imported_cad=True))
        )
        self.assertTrue(
            q.passes_quality_flags(
                Dummy(),
                {"ok": True, "has_imported_geometry": False},
                _flags(no_imported_cad=True),
            )
        )
        self.assertFalse(
            q.passes_quality_flags(
                Dummy(),
                {"ok": True, "has_imported_geometry": True},
                _flags(no_imported_cad=True),
            )
        )

    def test_limit_formulas_default_threshold_5(self):
        meta = {"ok": True, "param_has_formulas_count": 6}
        self.assertFalse(
            q.passes_quality_flags(Dummy(), meta, _flags(limit_formulas=True))
        )
        meta2 = {"ok": True, "param_has_formulas_count": 5}
        self.assertTrue(
            q.passes_quality_flags(Dummy(), meta2, _flags(limit_formulas=True))
        )

    def test_limit_ref_planes_sums_plane_and_line(self):
        meta = {
            "ok": True,
            "reference_plane_count": 6,
            "reference_line_count": 5,
        }
        self.assertFalse(
            q.passes_quality_flags(Dummy(), meta, _flags(limit_ref_planes=True))
        )
        meta2 = {
            "ok": True,
            "reference_plane_count": 4,
            "reference_line_count": 5,
        }
        self.assertTrue(
            q.passes_quality_flags(Dummy(), meta2, _flags(limit_ref_planes=True))
        )

    def test_all_count_flags_unknown_fail(self):
        for key in (
            "limit_dimensions",
            "limit_nested",
            "limit_params",
            "limit_materials",
        ):
            self.assertFalse(
                q.passes_quality_flags(Dummy(), None, _flags(**{key: True})),
                msg=key,
            )

    def test_not_huge_uses_size_kb_without_meta(self):
        # under 5 MB
        self.assertTrue(
            q.passes_quality_flags(Dummy(size_kb=1000.0), None, _flags(not_huge=True))
        )
        # over 5 MB
        self.assertFalse(
            q.passes_quality_flags(
                Dummy(size_kb=6 * 1024.0), None, _flags(not_huge=True)
            )
        )
        # missing size -> fail when flag on
        bare = Dummy()
        del bare.size_kb
        self.assertFalse(q.passes_quality_flags(bare, None, _flags(not_huge=True)))

    def test_and_combination(self):
        meta = {
            "ok": True,
            "type_count": 2,
            "is_shared_family": True,
            "has_imported_geometry": False,
        }
        flags = _flags(limit_types=True, shared_only=True, no_imported_cad=True)
        self.assertTrue(q.passes_quality_flags(Dummy(), meta, flags))
        meta["is_shared_family"] = False
        self.assertFalse(q.passes_quality_flags(Dummy(), meta, flags))

    def test_filter_families_helper(self):
        fams = [Dummy("a.rfa"), Dummy("b.rfa")]
        meta_by = {
            "a.rfa": {"ok": True, "type_count": 2},
            # b missing
        }
        out = q.filter_families(fams, meta_by, _flags(limit_types=True))
        self.assertEqual([x.path for x in out], ["a.rfa"])


if __name__ == "__main__":
    unittest.main()
