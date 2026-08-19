# -*- coding: utf-8 -*-
"""
Image / WPF helpers for loading PNG/JPEG bytes into BitmapImage objects.

Isolated here so UI dialogs do not mix bitmap plumbing with business logic.
"""
import os
import tempfile

import clr
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

import System
from System.IO import MemoryStream
from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption


def bitmap_from_png_bytes(image_bytes):
    """Load PNG or JPEG bytes into a WPF BitmapImage (IronPython-safe via temp file)."""
    if not image_bytes:
        return None
    is_jpeg = (
        len(image_bytes) >= 2
        and image_bytes[0] == "\xff"
        and image_bytes[1] == "\xd8")
    suffix = ".jpg" if is_jpeg else ".png"
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.write(fd, image_bytes)
        os.close(fd)
        bmp = BitmapImage()
        bmp.BeginInit()
        bmp.UriSource = System.Uri(tmp_path)
        bmp.CacheOption = BitmapCacheOption.OnLoad
        bmp.EndInit()
        bmp.Freeze()
        return bmp
    except Exception:
        try:
            text = image_bytes.decode("latin-1")
            buf = System.Text.Encoding.GetEncoding("latin-1").GetBytes(text)
            ms = MemoryStream(buf)
            bmp = BitmapImage()
            bmp.BeginInit()
            bmp.StreamSource = ms
            bmp.CacheOption = BitmapCacheOption.OnLoad
            bmp.EndInit()
            bmp.Freeze()
            return bmp
        except Exception:
            return None
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
