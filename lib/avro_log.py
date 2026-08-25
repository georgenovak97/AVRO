# -*- coding: utf-8 -*-
"""Small centralized logger for AVRO extension (best-effort, never raises)."""
import codecs
import os
import time

import config

try:
    unicode
except NameError:  # python3 tests
    unicode = str

_LOG_LOCK = config._IO_LOCK
_MAX_LOG_BYTES = 1024 * 1024
_LOG_BACKUP = config.LOG_FILE + u".1"


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
        with _LOG_LOCK:
            config._ensure_dir()
            try:
                if os.path.isfile(config.LOG_FILE):
                    if os.path.getsize(config.LOG_FILE) >= _MAX_LOG_BYTES:
                        if os.path.isfile(_LOG_BACKUP):
                            os.remove(_LOG_BACKUP)
                        os.rename(config.LOG_FILE, _LOG_BACKUP)
            except Exception:
                pass
            line = u"[{}] [{}] {}\n".format(
                time.strftime("%Y-%m-%d %H:%M:%S"),
                _u(scope),
                _u(message),
            )
            with codecs.open(config.LOG_FILE, "a", "utf-8") as f:
                f.write(line)
    except Exception:
        pass


def event(scope, name, fields=None):
    """Write a bounded diagnostic event; callers should pass no local paths."""
    parts = [u"event={}".format(_u(name))]
    for key, value in (fields or {}).items():
        parts.append(u"{}={}".format(_u(key), _u(value)))
    write(scope, u" ".join(parts))


def exception(scope, ex):
    try:
        write(scope, u"{}: {}".format(type(ex).__name__, _u(ex)))
    except Exception:
        pass
