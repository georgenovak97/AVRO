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

import family_inspector as fi  # noqa: E402


class Dummy(object):
    def __init__(self, path='x.rfa'):
        self.path = path


class FamilyInspectorTriStateTests(unittest.TestCase):
    def setUp(self):
        self._orig_load_cached = fi.load_cached

    def tearDown(self):
        fi.load_cached = self._orig_load_cached

    def _set_cached(self, data):
        fi.load_cached = lambda _p: data

    def test_cached_bool_key_unknown_when_no_cache(self):
        self._set_cached(None)
        self.assertEqual(fi._cached_bool_key('a.rfa', 'has_imported_geometry'), fi.BOOL_UNKNOWN)

    def test_cached_bool_key_unknown_when_missing_key(self):
        self._set_cached({'ok': True})
        self.assertEqual(fi._cached_bool_key('a.rfa', 'has_imported_geometry'), fi.BOOL_UNKNOWN)

    def test_cached_bool_key_yes_no_from_values(self):
        self._set_cached({'ok': True, 'has_imported_geometry': True})
        self.assertEqual(fi._cached_bool_key('a.rfa', 'has_imported_geometry'), fi.BOOL_YES)
        self._set_cached({'ok': True, 'has_imported_geometry': False})
        self.assertEqual(fi._cached_bool_key('a.rfa', 'has_imported_geometry'), fi.BOOL_NO)

    def test_has_imported_geometry_of_fi_unknown_without_cache(self):
        self._set_cached(None)
        self.assertEqual(fi.has_imported_geometry_of_fi(Dummy()), fi.BOOL_UNKNOWN)


    def test_category_of_returns_cached_revit_category(self):
        self._set_cached({'ok': True, 'category': 'Doors'})
        self.assertEqual(fi.category_of(Dummy('a.rfa')), 'Doors')

    def test_category_of_empty_without_cache(self):
        self._set_cached(None)
        self.assertEqual(fi.category_of(Dummy('a.rfa')), '')

    def test_collect_filter_options_keeps_unknown(self):
        self._set_cached({'ok': True, 'has_imported_geometry': None, 'has_shared_nested': 'unknown',
                          'is_shared_family': False, 'work_plane_based': True, 'always_vertical': None,
                          'hosting': 'unknown', 'placement': '', 'revit_format': ''})
        opts = fi.collect_filter_options([Dummy('x.rfa')])
        self.assertIn('unknown', opts['has_imported_geometry'])
        self.assertIn('unknown', opts['has_shared_nested'])
        self.assertIn('no', opts['is_shared_family'])
        self.assertIn('yes', opts['work_plane_based'])
        self.assertIn('unknown', opts['always_vertical'])

    def test_empty_meta_bools_are_unknown_not_false(self):
        meta = fi._empty_meta('x.rfa')
        self.assertIs(meta.get('is_shared_family'), None)
        self.assertIs(meta.get('work_plane_based'), None)
        self.assertIs(meta.get('always_vertical'), None)
        self.assertIs(meta.get('has_imported_geometry'), None)
        self.assertIs(meta.get('has_shared_nested'), None)
        self.assertEqual(fi._bool_filter_key(meta.get('is_shared_family')), fi.BOOL_UNKNOWN)

    def test_normalize_revit_label_stable(self):
        self.assertEqual(fi.normalize_revit_label('2024'), 'R24')
        self.assertEqual(fi.normalize_revit_label('R22'), 'R22')
        self.assertEqual(fi.normalize_revit_label('r19'), 'R19')
        self.assertEqual(fi.normalize_revit_label('Autodesk Revit 2021'), 'R21')

    def test_revit_format_of_cache_and_scanner_agree(self):
        class Dummy(object):
            def __init__(self):
                self.path = 'a.rfa'
                self.revit_version = 'R22'

        self._set_cached(None)
        self.assertEqual(fi.revit_format_of(Dummy()), 'R22')
        self._set_cached({'ok': True, 'revit_format': '2024'})
        self.assertEqual(fi.revit_format_of(Dummy()), 'R24')

    def test_collect_filter_options_versions_without_cache(self):
        class Dummy(object):
            def __init__(self, path, ver):
                self.path = path
                self.revit_version = ver

        self._set_cached(None)
        opts = fi.collect_filter_options([Dummy('a.rfa', 'R22'), Dummy('b.rfa', 'R24')])
        self.assertEqual(opts['revit_formats'], ['R22', 'R24'])


if __name__ == '__main__':
    unittest.main()
