# -*- coding: utf-8 -*-
"""Small centralized logger for AVRO extension (best-effort, never raises)."""
import codecs
import time

import config

try:
    unicode
except NameError:  # python3 tests
    unicode = str


def _u(text):
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    if isinstance(text, str):
        for enc in ("utf-8", "cp1251", "latin-1"):
            try:
                return unicode(text, enc)
            except Exception:
                continue
    try:
        return unicode(text)
    except Exception:
        return u""


def write(scope, message):
    """Write one structured line into tmp/cache.log."""
    try:
        config._ensure_dir()
        line = u"[{}] [{}] {}\n".format(
            time.strftime("%Y-%m-%d %H:%M:%S"),
            _u(scope),
            _u(message),
        )
        with codecs.open(config.LOG_FILE, "a", "utf-8") as f:
            f.write(line)
    except Exception:
        pass


def exception(scope, ex):
    try:
        write(scope, u"{}: {}".format(type(ex).__name__, _u(ex)))
    except Exception:
        pass
