# -*- coding: utf-8 -*-
"""
Extract embedded preview images from Revit .rfa / .rvt compound files.

Reads RevitPreview* OLE streams (via System.IO.Packaging), including
gzip-framed DEFLATE payloads used in Revit 2021+ and JPEG thumbnails
where present. Falls back to scanning the raw file.
"""
import os
import hashlib
import struct

THUMB_CACHE_DIR = os.path.join(
    os.getenv("APPDATA", ""), "pyRevit", "AVRO", "thumbs")

_PNG_SIG = "\x89PNG\r\n\x1a\n"
_JPEG_SOI = "\xff\xd8"
_PREVIEW_STREAMS = (
    "RevitPreview5.0",
    "RevitPreview4.0",
    "RevitPreview3.0",
    "RevitPreview2.0",
    "RevitPreview",
)

_storage_root_type = None
_storage_open_flags = None
_storage_opened = False


def _ensure_cache_dir():
    if not os.path.exists(THUMB_CACHE_DIR):
        os.makedirs(THUMB_CACHE_DIR)


def _cache_key(rfa_path):
    st = os.stat(rfa_path)
    raw = u"{}|{}".format(os.path.normcase(rfa_path), int(st.st_mtime)).encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def _cache_path(rfa_path):
    return os.path.join(THUMB_CACHE_DIR, _cache_key(rfa_path) + ".png")


def _cache_path_jpeg(rfa_path):
    return os.path.join(THUMB_CACHE_DIR, _cache_key(rfa_path) + ".jpg")


def _write_cache_jpeg(cache_path, jpeg_bytes):
    _ensure_cache_dir()
    with open(cache_path, "wb") as f:
        f.write(jpeg_bytes)


def _read_cache_jpeg(cache_path):
    if not os.path.isfile(cache_path):
        return None
    try:
        data = _read_file_bytes(cache_path)
        if len(data) >= 3 and data[0] == "\xff" and data[1] == "\xd8":
            return data
    except Exception:
        pass
    return None


def _read_file_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _write_cache(cache_path, png_bytes):
    _ensure_cache_dir()
    with open(cache_path, "wb") as f:
        f.write(png_bytes)


def _read_cache(cache_path):
    if not os.path.isfile(cache_path):
        return None
    try:
        data = _read_file_bytes(cache_path)
        if data.startswith(_PNG_SIG):
            return data
    except Exception:
        pass
    return None


def _slice_png(data, start):
    pos = start + 8
    data_len = len(data)
    while pos + 12 <= data_len:
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        pos += 12 + length
        if pos > data_len:
            return None
        if chunk_type == "IEND":
            return data[start:pos]
    return None


def _find_png_in_buffer(raw):
    """Return PNG bytes from a RevitPreview stream or file blob."""
    if not raw:
        return None

    idx = raw.find(_PNG_SIG)
    if idx >= 0:
        png = _slice_png(raw, idx)
        if png:
            return png

    # State-machine search (Revit metadata before PNG signature)
    marker_found = False
    starting_offset = 0
    previous_value = 0
    for i in range(len(raw)):
        current_value = ord(raw[i])
        if current_value == 0x89:
            marker_found = True
            starting_offset = i
            previous_value = current_value
            continue

        if not marker_found:
            continue

        if current_value == 0x50 and previous_value == 0x89:
            previous_value = current_value
            continue
        if current_value == 0x4E and previous_value == 0x50:
            previous_value = current_value
            continue
        if current_value == 0x47 and previous_value == 0x4E:
            previous_value = current_value
            continue
        if current_value == 0x0D and previous_value == 0x47:
            previous_value = current_value
            continue
        if current_value == 0x0A and previous_value == 0x0D:
            previous_value = current_value
            continue
        if current_value == 0x1A and previous_value == 0x0A:
            previous_value = current_value
            continue
        if current_value == 0x0A and previous_value == 0x1A:
            png = _slice_png(raw, starting_offset)
            if png:
                return png
            marker_found = False
            continue

        marker_found = False

    return None


def _maybe_inflate_truncated_gzip(raw):
    """
    Newer Revit OLE preview streams use a gzip-like header + raw DEFLATE
    (often no standard gzip trailer). Try raw DEFLATE after small skips.
    """
    if not raw or len(raw) < 20:
        return None
    if raw[0] != "\x1f" or raw[1] != "\x8b":
        return None
    try:
        import zlib
    except Exception:
        return None
    for skip in (10, 12, 14, 16):
        if len(raw) <= skip:
            continue
        try:
            out = zlib.decompress(raw[skip:], -15)
            if out and len(out) > 32:
                return out
        except Exception:
            continue
    return None


def _preview_decode_candidates(raw):
    """Raw stream bytes plus inflated variant when gzip-framed."""
    if not raw:
        return
    yield raw
    inflated = _maybe_inflate_truncated_gzip(raw)
    if inflated and inflated != raw:
        yield inflated


def _slice_jpeg(data, start):
    end = data.find("\xff\xd9", start + 2)
    if end < 0:
        return None
    return data[start : end + 2]


def _extract_jpeg_from_bytes(data):
    """Largest valid JPEG blob (SOI … EOI)."""
    if not data:
        return None
    best = None
    best_len = 0
    search_from = 0
    while True:
        idx = data.find(_JPEG_SOI, search_from)
        if idx < 0:
            break
        jpg = _slice_jpeg(data, idx)
        if jpg and len(jpg) > best_len:
            best = jpg
            best_len = len(jpg)
        search_from = idx + 1
    return best


def _extract_image_from_bytes(data):
    """
    Return (image_bytes, 'png'|'jpeg') or (None, None).
    Tries raw and gzip-framed DEFLATE payloads (Revit 2021+ preview streams).
    """
    if not data:
        return None, None
    best_png, best_jpg = None, None
    png_len, jpg_len = 0, 0
    for cand in _preview_decode_candidates(data):
        png = _extract_png_from_bytes(cand)
        if png and len(png) > png_len:
            best_png, png_len = png, len(png)
        jpg = _extract_jpeg_from_bytes(cand)
        if jpg and len(jpg) > jpg_len:
            best_jpg, jpg_len = jpg, len(jpg)
    if best_png:
        return best_png, "png"
    if best_jpg:
        return best_jpg, "jpeg"
    return None, None


def _extract_png_from_bytes(data):
    best = None
    best_len = 0
    search_from = 0
    while True:
        idx = data.find(_PNG_SIG, search_from)
        if idx < 0:
            break
        png = _slice_png(data, idx)
        if png and len(png) > best_len:
            best = png
            best_len = len(png)
        search_from = idx + 1
    if best:
        return best
    return _find_png_in_buffer(data)


def _init_storage_api():
    global _storage_root_type, _storage_open_flags, _storage_opened
    if _storage_opened:
        return _storage_root_type is not None
    _storage_opened = True
    try:
        import clr
        clr.AddReference("WindowsBase")
        from System.IO.Packaging import StorageInfo
        from System.Reflection import BindingFlags

        sr_type = StorageInfo.Assembly.GetType("System.IO.Packaging.StorageRoot")
        if sr_type is None:
            return False

        _storage_root_type = sr_type
        _storage_open_flags = (
            BindingFlags.NonPublic | BindingFlags.Static |
            BindingFlags.Public | BindingFlags.InvokeMethod)
        return True
    except Exception:
        return False


def _read_stream_bytes(stream_info):
    """Read entire OLE stream into a Python byte string."""
    from System import Array, Byte
    from System.IO import FileMode, FileAccess

    reader = stream_info.GetStream(FileMode.Open, FileAccess.Read)
    try:
        length = int(reader.Length)
        if length <= 0:
            return None
        buf = Array.CreateInstance(Byte, length)
        read = int(reader.Read(buf, 0, length))
        if read <= 0:
            return None
        return "".join(chr(int(buf[i])) for i in range(read))
    finally:
        reader.Close()


def _list_preview_stream_payloads(rfa_path):
    """
    Return raw bytes from preview-related OLE streams (priority order,
    then any stream whose name contains 'preview').
    """
    payloads = []
    if not _init_storage_api():
        return payloads
    try:
        from System import Array, Object
        from System.IO import FileMode, FileAccess, FileShare

        net_path = rfa_path

        args = Array[Object]([
            net_path, FileMode.Open, FileAccess.Read, FileShare.Read])
        st_info = _storage_root_type.InvokeMember(
            "Open", _storage_open_flags, None, None, args)
        if st_info is None:
            return payloads

        by_name = {}
        for stream_info in st_info.GetStreams():
            try:
                nm = stream_info.Name
                if not isinstance(nm, basestring):
                    nm = unicode(nm)
            except Exception:
                nm = u""
            by_name[nm] = stream_info

        seen = set()
        for wanted in _PREVIEW_STREAMS:
            si = by_name.get(wanted)
            if si is None:
                continue
            data = _read_stream_bytes(si)
            if data:
                seen.add(wanted)
                payloads.append(data)

        for name, si in by_name.items():
            try:
                if "preview" not in name.lower():
                    continue
            except Exception:
                continue
            if name in seen:
                continue
            data = _read_stream_bytes(si)
            if data and len(data) > 64:
                payloads.append(data)
    except Exception:
        pass
    return payloads


def read_cached_png_bytes(rfa_path):
    """Return cached preview bytes (PNG or JPEG), or None."""
    if not rfa_path or not os.path.isfile(rfa_path):
        return None
    hit = _read_cache(_cache_path(rfa_path))
    if hit:
        return hit
    return _read_cache_jpeg(_cache_path_jpeg(rfa_path))


def extract_preview_png_bytes(rfa_path):
    """
    Return embedded preview image bytes (PNG or JPEG), or None.
    Uses disk cache keyed by path + modification time.
    """
    if not rfa_path or not os.path.isfile(rfa_path):
        return None

    hit = _read_cache(_cache_path(rfa_path))
    if hit:
        return hit
    hit = _read_cache_jpeg(_cache_path_jpeg(rfa_path))
    if hit:
        return hit

    img_bytes = None
    kind = None

    for blob in _list_preview_stream_payloads(rfa_path):
        img_bytes, kind = _extract_image_from_bytes(blob)
        if img_bytes:
            break

    if img_bytes is None:
        try:
            file_data = _read_file_bytes(rfa_path)
            img_bytes, kind = _extract_image_from_bytes(file_data)
        except Exception:
            pass

    if img_bytes:
        try:
            if kind == "jpeg":
                _write_cache_jpeg(_cache_path_jpeg(rfa_path), img_bytes)
            else:
                _write_cache(_cache_path(rfa_path), img_bytes)
        except Exception:
            pass
    return img_bytes
