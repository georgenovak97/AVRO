# -*- coding: utf-8 -*-
import builtins
import os
import shutil
import sys
import tempfile
import unittest

if not hasattr(builtins, "unicode"):
    builtins.unicode = str
if not hasattr(builtins, "basestring"):
    builtins.basestring = (str, bytes)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB = os.path.join(ROOT, "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import config  # noqa: E402
import family_scanner as scanner  # noqa: E402
import library_cache as lc  # noqa: E402


class FakeFamilyInfo(object):
    def __init__(self, path, library_root):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.category = u"Generic Models"
        self.size_kb = 1
        self.modified = u"2026-01-01"
        self.folder = os.path.basename(os.path.dirname(path))
        self.library_root = library_root
        self.rel_path = self.folder
        self.revit_version = u"R24"
        self.preview = None


class LibraryCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="avro-test-cache-")

        self._cfg_backup = {
            "CONFIG_DIR": config.CONFIG_DIR,
            "CONFIG_FILE": config.CONFIG_FILE,
            "RECENT_FILE": config.RECENT_FILE,
            "LOG_FILE": config.LOG_FILE,
            "THUMB_CACHE_DIR": config.THUMB_CACHE_DIR,
        }
        config.CONFIG_DIR = self.tmp
        config.CONFIG_FILE = os.path.join(self.tmp, "config.json")
        config.RECENT_FILE = os.path.join(self.tmp, "recent_families.json")
        config.LOG_FILE = os.path.join(self.tmp, "cache.log")
        config.THUMB_CACHE_DIR = os.path.join(self.tmp, "thumbs")

        self._lc_backup = {
            "META_FILE": lc.META_FILE,
            "PICKLE_FILE": lc.PICKLE_FILE,
            "INDEX_FILE": lc.INDEX_FILE,
            "LOG_FILE": lc.LOG_FILE,
            "_unicode_to_utf8": lc._unicode_to_utf8,
        }
        lc.META_FILE = os.path.join(self.tmp, "library_meta.json")
        lc.PICKLE_FILE = os.path.join(self.tmp, "library_index.pkl")
        lc.INDEX_FILE = os.path.join(self.tmp, "library_index.json")
        lc.LOG_FILE = os.path.join(self.tmp, "cache.log")
        # Python3 test compatibility: keep JSON values as str, not bytes.
        lc._unicode_to_utf8 = lambda v: v

    def tearDown(self):
        for k, v in self._cfg_backup.items():
            setattr(config, k, v)
        for k, v in self._lc_backup.items():
            setattr(lc, k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_scan(self):
        root = os.path.join(self.tmp, "libroot")
        cat = os.path.join(root, "Doors")
        os.makedirs(cat)
        path = os.path.join(cat, "Door_A.rfa")
        with open(path, "wb") as f:
            f.write(b"x")

        fi = FakeFamilyInfo(path=path, library_root=root)
        node = scanner.FolderNode(root)
        node.families.append(fi)
        roots = [node]
        return {
            "roots": roots,
            "all": [fi],
            "index": scanner.index_folder_tree(roots),
        }, fi

    def test_cache_key_is_order_independent(self):
        p1 = os.path.join(self.tmp, "B")
        p2 = os.path.join(self.tmp, "A")
        key = lc.cache_key([p1, p2])
        expected = tuple(sorted([lc._norm_path(p1), lc._norm_path(p2)]))
        self.assertEqual(key, expected)

    def test_key_hash_stable(self):
        key = (lc._norm_path(os.path.join(self.tmp, "A")),)
        h1 = lc.key_hash(key)
        h2 = lc.key_hash(key)
        self.assertEqual(h1, h2)
        self.assertTrue(h1)

    def test_save_load_roundtrip(self):
        scan, fi = self._make_scan()
        key = lc.cache_key([fi.library_root])
        ok, msg = lc.save(key, scan, preview_miss=set([fi.path]))
        self.assertTrue(ok, msg)

        loaded, miss, err = lc.load(key)
        self.assertIsNone(err)
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded["all"]), 1)
        self.assertEqual(loaded["all"][0].name, fi.name)
        self.assertIn(lc._norm_path(fi.path), miss)

    def test_preview_miss_sidecar_roundtrip(self):
        _scan, fi = self._make_scan()
        key = lc.cache_key([fi.library_root])
        signature = {
            "mtime": os.path.getmtime(fi.path),
            "size": os.path.getsize(fi.path),
        }

        self.assertTrue(lc.save_preview_misses(
            key, {fi.path: signature}))
        loaded = lc.load_preview_misses(key)
        path = lc._norm_path(fi.path)
        self.assertEqual(loaded[path], signature)

    def test_preview_miss_sidecar_rejects_wrong_key_and_legacy_entries(self):
        _scan, fi = self._make_scan()
        key = lc.cache_key([fi.library_root])
        path = lc.preview_miss_file(key)
        config._ensure_dir()
        with open(path, "w") as stream:
            stream.write(
                '{"version": 1, "key_hash": "wrong", '
                '"entries": {"%s": [1, 2]}}' % fi.path)

        self.assertEqual(lc.load_preview_misses(key), {})

        with open(path, "w") as stream:
            stream.write(
                '{"version": 1, "key_hash": "%s", '
                '"entries": {"%s": [1, 2]}}'
                % (lc.key_hash(key), fi.path))
        self.assertEqual(lc.load_preview_misses(key), {})

    def test_preview_miss_sidecar_clear_removes_entries(self):
        _scan, fi = self._make_scan()
        key = lc.cache_key([fi.library_root])
        self.assertTrue(lc.save_preview_misses(key, {
            fi.path: {
                "mtime": os.path.getmtime(fi.path),
                "size": os.path.getsize(fi.path),
            }}))
        lc.clear_preview_misses(key)
        self.assertEqual(lc.load_preview_misses(key), {})


if __name__ == "__main__":
    unittest.main()
