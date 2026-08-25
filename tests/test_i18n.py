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

import i18n  # noqa: E402


class I18nTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language(u"en")

    def test_set_language_ru_en_and_fallback(self):
        i18n.set_language(u"ru")
        self.assertEqual(i18n.get_language(), u"ru")

        i18n.set_language(u"en")
        self.assertEqual(i18n.get_language(), u"en")

        i18n.set_language(u"de")
        self.assertEqual(i18n.get_language(), u"en")

    def test_translate_known_key_in_ru(self):
        i18n.set_language(u"ru")
        self.assertEqual(i18n.t(u"btn_load"), u"Загрузка")
        self.assertEqual(i18n.t(u"props_unknown"), u"Неизвестно")

    def test_translate_known_key_in_en(self):
        i18n.set_language(u"en")
        self.assertEqual(i18n.t(u"btn_load"), u"Load")
        self.assertEqual(i18n.t(u"props_unknown"), u"Unknown")

    def test_opening_status_is_preparing(self):
        i18n.set_language(u"ru")
        self.assertEqual(i18n.t(u"opening"), u"Подготовка…")
        i18n.set_language(u"en")
        self.assertEqual(i18n.t(u"opening"), u"Preparing…")

    def test_missing_key_returns_key_name(self):
        i18n.set_language(u"en")
        self.assertEqual(i18n.t(u"__missing_key__"), u"__missing_key__")

    def test_formatting_params(self):
        i18n.set_language(u"en")
        self.assertEqual(i18n.t(u"loaded_n", n=3), u"Loaded: 3")

    def test_preview_completion_is_short(self):
        i18n.set_language(u"ru")
        self.assertEqual(i18n.t(u"previews_done", n=80), u"Готово")
        i18n.set_language(u"en")
        self.assertEqual(i18n.t(u"previews_done", n=80), u"Done")

    def test_transaction_names_have_avro_prefix(self):
        for lang in (u"ru", u"en"):
            i18n.set_language(lang)
            for key in (u"txn_activate", u"txn_load", u"txn_load_family"):
                self.assertTrue(i18n.t(key, label=u"Family").startswith(u"AVRO: "))

    def test_lang_override_argument(self):
        i18n.set_language(u"ru")
        self.assertEqual(i18n.t(u"btn_load", lang=u"en"), u"Load")


if __name__ == "__main__":
    unittest.main()
