# -*- coding: utf-8 -*-
"""
Read family metadata from .rfa via Revit API (OpenDocumentFile).

Results are cached under tmp/family_meta/ by path + mtime.
"""
from __future__ import print_function

import os
import json
import hashlib
import codecs
import time

import config
import avro_log
import rfa_version
import re

try:
    from Autodesk.Revit.DB import (
        BasicFileInfo,
        BuiltInParameter,
        FilteredElementCollector,
        ImportInstance,
        FamilyInstance,
        ReferencePlane,
        Dimension,
        Material,
        Family as RevitFamily,
        OpenOptions,
        ModelPathUtils,
    )
    _API_OK = True
except Exception:
    _API_OK = False

META_DIR = os.path.join(config.CONFIG_DIR, "family_meta")
CACHE_VERSION = 1

_RE_R_LABEL = re.compile(r"^R?(\d{2})$", re.I)
_RE_YEAR = re.compile(r"(20\d{2})")


def normalize_revit_label(value):
    """Normalize any version string to short label R22/R24 when possible."""
    s = _u(value).strip()
    if not s:
        return u""
    m = _RE_R_LABEL.match(s)
    if m:
        try:
            return u"R{:02d}".format(int(m.group(1)))
        except Exception:
            return s.upper() if s[:1].upper() == u"R" else u"R" + s
    # Prefer rfa_version helpers when available
    try:
        lab = rfa_version._label_from_format_string(s)
        if lab:
            return lab
    except Exception:
        pass
    m = _RE_YEAR.search(s)
    if m:
        try:
            return rfa_version.year_to_label(m.group(1))
        except Exception:
            pass
    return s

# Stable filter keys (UI maps via i18n)
HOST_ALL = u"all"
HOST_CEILING = u"ceiling"
HOST_WALL = u"wall"
HOST_FLOOR = u"floor"
HOST_ROOF = u"roof"
HOST_FACE = u"face"
HOST_INDEPENDENT = u"independent"
HOST_UNKNOWN = u"unknown"
HOST_OTHER = u"other"
BOOL_YES = u"yes"
BOOL_NO = u"no"
BOOL_UNKNOWN = u"unknown"

HOST_FILTER_KEYS = (
    HOST_ALL,
    HOST_CEILING,
    HOST_WALL,
    HOST_FLOOR,
    HOST_ROOF,
    HOST_FACE,
    HOST_INDEPENDENT,
    HOST_UNKNOWN,
    HOST_OTHER,
)

_HOSTING_BY_INT = {
    0: HOST_INDEPENDENT,
    1: HOST_WALL,
    2: HOST_FLOOR,
    3: HOST_CEILING,
    4: HOST_ROOF,
    5: HOST_FACE,
}


def _u(text):
    if text is None:
        return u""
    if isinstance(text, unicode):
        return text
    try:
        return unicode(text)
    except Exception:
        return u""


def _empty_meta(path=u""):
    return {
        "version": CACHE_VERSION,
        "path": _u(path),
        "ok": False,
        "error": u"",
        "category": u"",
        "hosting": HOST_UNKNOWN,
        "placement": u"",
        # tri-state booleans: None = unknown until successful inspect
        "is_shared_family": None,
        "work_plane_based": None,
        "always_vertical": None,
        "has_imported_geometry": None,
        "has_shared_nested": None,
        "shared_nested": [],
        "types": [],
        "type_count": 0,
        "param_total_count": 0,
        "param_instance_count": 0,
        "param_type_count": 0,
        "param_has_formulas": False,
        "param_has_formulas_count": 0,
        "reference_plane_count": 0,
        "reference_line_count": 0,
        "dimension_count": 0,
        "nested_family_count": 0,
        "material_count": 0,
        "file_size_mb": 0.0,
        "revit_format": u"",
        "inspected_at": u"",
    }


def _ensure_meta_dir():
    if not os.path.isdir(META_DIR):
        os.makedirs(META_DIR)


def _cache_key(rfa_path):
    try:
        st = os.stat(rfa_path)
        raw = u"{}|{}".format(
            os.path.normcase(os.path.abspath(rfa_path)),
            int(st.st_mtime),
        ).encode("utf-8")
    except Exception:
        raw = _u(rfa_path).encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def _cache_path(rfa_path):
    return os.path.join(META_DIR, _cache_key(rfa_path) + ".json")


def load_cached(rfa_path):
    """Return cached meta dict or None."""
    try:
        p = _cache_path(rfa_path)
        if not os.path.isfile(p):
            return None
        with codecs.open(p, "r", "utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
            return None
        return data
    except Exception:
        return None


_last_meta_prune = 0


def prune_cache(max_files=5000, max_age_days=30, force=False):
    """Prune orphaned/old inspect cache files by age and count limit."""
    global _last_meta_prune
    now = time.time()
    if not force and (now - _last_meta_prune < 300):
        return
    _last_meta_prune = now

    if not os.path.isdir(META_DIR):
        return

    try:
        max_age_sec = max_age_days * 86400
        entries = []
        for name in os.listdir(META_DIR):
            if not name.endswith(".json"):
                continue
            path = os.path.join(META_DIR, name)
            try:
                st = os.stat(path)
                mtime = st.st_mtime
                if (now - mtime) > max_age_sec:
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                    continue
                entries.append((mtime, path))
            except Exception:
                pass

        if len(entries) > max_files:
            entries.sort(key=lambda x: x[0])
            to_remove = len(entries) - max_files
            for i in range(to_remove):
                try:
                    os.remove(entries[i][1])
                except Exception:
                    pass
    except Exception as ex:
        avro_log.exception("family_meta.prune", ex)


def save_cached(rfa_path, meta):
    try:
        _ensure_meta_dir()
        data = dict(meta or _empty_meta(rfa_path))
        data["version"] = CACHE_VERSION
        data["path"] = _u(rfa_path)
        data["inspected_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if isinstance(text, str):
            text = _u(text)
        with codecs.open(_cache_path(rfa_path), "w", "utf-8") as f:
            f.write(text)
        prune_cache()
    except Exception as ex:
        avro_log.exception("family_meta.save", ex)


def clear_cache():
    if not os.path.isdir(META_DIR):
        return
    try:
        for name in os.listdir(META_DIR):
            path = os.path.join(META_DIR, name)
            if os.path.isfile(path) and name.endswith(".json"):
                try:
                    os.remove(path)
                except Exception:
                    pass
    except Exception as ex:
        avro_log.exception("family_meta.clear", ex)


def _element_name(element):
    if element is None:
        return u""
    try:
        from Autodesk.Revit.DB import Element
        return _u(Element.Name.__get__(element, type(element)))
    except Exception:
        pass
    try:
        return _u(getattr(element, "Name"))
    except Exception:
        return u""


def _hosting_from_owner(owner):
    """Map FAMILY_HOSTING_BEHAVIOR / FamilyPlacementType to filter key."""
    if owner is None:
        return HOST_UNKNOWN, u""

    placement = u""
    try:
        placement = _u(str(owner.FamilyPlacementType))
    except Exception:
        pass

    try:
        param = owner.get_Parameter(BuiltInParameter.FAMILY_HOSTING_BEHAVIOR)
        if param is not None and param.HasValue:
            try:
                val = int(param.AsInteger())
            except Exception:
                val = -1
            host = _HOSTING_BY_INT.get(val)
            if host:
                return host, placement
    except Exception:
        pass

    # Placement fallbacks
    pl = placement.lower()
    if u"workplane" in pl or u"face" in pl:
        return HOST_FACE, placement
    if u"curve" in pl or u"onelevel" in pl or u"twolevel" in pl:
        return HOST_INDEPENDENT, placement
    if placement:
        return HOST_OTHER, placement
    return HOST_UNKNOWN, placement


def _inspect_document(doc, rfa_path):
    meta = _empty_meta(rfa_path)
    meta["ok"] = True

    owner = None
    try:
        owner = doc.OwnerFamily
    except Exception:
        owner = None

    try:
        if owner is not None and owner.FamilyCategory is not None:
            meta["category"] = _element_name(owner.FamilyCategory)
    except Exception:
        pass

    host, placement = _hosting_from_owner(owner)
    meta["hosting"] = host
    meta["placement"] = placement

    # Boolean flags useful for stable filters
    try:
        meta["is_shared_family"] = bool(_is_family_shared(owner))
    except Exception:
        meta["is_shared_family"] = None

    try:
        pl = (placement or u"").lower()
        meta["work_plane_based"] = (u"workplane" in pl) or (u"work plane" in pl) or (u"work_plane" in pl)
    except Exception:
        meta["work_plane_based"] = None

    try:
        always = None
        try:
            if owner is not None:
                p_av = owner.get_Parameter(BuiltInParameter.FAMILY_ALWAYS_VERTICAL)
                if p_av is not None and p_av.HasValue:
                    always = int(p_av.AsInteger()) == 1
                else:
                    always = False
        except Exception:
            always = None
        meta["always_vertical"] = always
    except Exception:
        meta["always_vertical"] = None

    # Types
    types = []
    try:
        fm = doc.FamilyManager
        for t in fm.Types:
            try:
                name = _u(t.Name).strip()
            except Exception:
                name = u""
            if name:
                types.append(name)
    except Exception:
        pass
    types = sorted(set(types), key=lambda s: s.lower())
    meta["types"] = types
    meta["type_count"] = len(types)

    # Imported geometry (CAD / ImportInstance)
    try:
        n_imp = FilteredElementCollector(doc).OfClass(ImportInstance).GetElementCount()
        meta["has_imported_geometry"] = int(n_imp) > 0
    except Exception:
        meta["has_imported_geometry"] = None

    # Nested families and shared-nested names
    shared = []
    nested_ids = set()
    nested_ok = False
    try:
        for inst in FilteredElementCollector(doc).OfClass(FamilyInstance):
            try:
                sym = getattr(inst, "Symbol", None)
                fam = getattr(sym, "Family", None) if sym is not None else None
                fid = getattr(fam, "Id", None)
                if fid is not None:
                    nested_ids.add(fid.IntegerValue)
                    if _is_family_shared(fam):
                        name = _element_name(fam)
                        if name:
                            shared.append(name)
            except Exception:
                continue
        nested_ok = True
    except Exception:
        nested_ok = False
    shared = sorted(set(shared), key=lambda s: s.lower())
    meta["shared_nested"] = shared
    if nested_ok:
        meta["has_shared_nested"] = len(shared) > 0
        meta["nested_family_count"] = int(len(nested_ids))
    else:
        meta["has_shared_nested"] = None
        meta["nested_family_count"] = None

    # Extra complexity counters for quality filters
    ref_planes = 0
    ref_lines = 0
    try:
        for rp in FilteredElementCollector(doc).OfClass(ReferencePlane):
            try:
                if bool(getattr(rp, "IsReferenceLine", False)):
                    ref_lines += 1
                else:
                    ref_planes += 1
            except Exception:
                ref_planes += 1
    except Exception:
        pass
    meta["reference_plane_count"] = int(ref_planes)
    meta["reference_line_count"] = int(ref_lines)
    try:
        meta["dimension_count"] = int(
            FilteredElementCollector(doc).OfClass(Dimension).GetElementCount()
        )
    except Exception:
        meta["dimension_count"] = 0
    try:
        meta["material_count"] = int(
            FilteredElementCollector(doc).OfClass(Material).GetElementCount()
        )
    except Exception:
        meta["material_count"] = 0
    try:
        meta["file_size_mb"] = round(float(os.path.getsize(rfa_path)) / (1024.0 * 1024.0), 3)
    except Exception:
        meta["file_size_mb"] = 0.0

    # Revit version: normalize to R22/R24 labels for stable filters
    raw_ver = u""
    try:
        raw_ver = _u(doc.Application.VersionNumber)
    except Exception:
        raw_ver = u""
    if not raw_ver:
        try:
            info = BasicFileInfo.Extract(rfa_path)
            if info is not None and info.Format:
                raw_ver = _u(info.Format)
        except Exception:
            raw_ver = u""
    meta["revit_format"] = normalize_revit_label(raw_ver)

    # FamilyManager parameter stats (counts only; cheap vs full param listing)
    try:
        fm = doc.FamilyManager
        total = 0
        inst = 0
        typ = 0
        has_formulas = False
        formulas_count = 0
        try:
            params = fm.Parameters
        except Exception:
            params = None
        if params is not None:
            for fp in params:
                try:
                    total += 1
                except Exception:
                    pass
                try:
                    if fp.IsInstance:
                        inst += 1
                    else:
                        typ += 1
                except Exception:
                    pass
                # Formula presence varies by API; keep it defensive.
                try:
                    f = fp.Formula
                except Exception:
                    f = None
                try:
                    if f:
                        formulas_count += 1
                        has_formulas = True
                except Exception:
                    pass
        meta["param_total_count"] = total
        meta["param_instance_count"] = inst
        meta["param_type_count"] = typ
        meta["param_has_formulas"] = bool(has_formulas)
        meta["param_has_formulas_count"] = formulas_count
    except Exception:
        pass

    return meta


def _is_family_shared(fam):
    if fam is None:
        return False
    try:
        param = fam.get_Parameter(BuiltInParameter.FAMILY_SHARED)
        if param is not None and param.HasValue:
            return int(param.AsInteger()) == 1
    except Exception:
        pass
    return False


def inspect(rfa_path, app=None, use_cache=True):
    """
    Inspect .rfa. Returns meta dict (never None).

    Opens the family document read-only in the background and closes it.
    Must run on Revit main thread.
    """
    path = _u(rfa_path)
    if not path or not os.path.isfile(path):
        meta = _empty_meta(path)
        meta["error"] = u"file_not_found"
        return meta

    if use_cache:
        cached = load_cached(path)
        if cached is not None:
            return cached

    if not _API_OK:
        meta = _empty_meta(path)
        meta["error"] = u"revit_api_unavailable"
        return meta

    if app is None:
        try:
            import __revit__
            app = __revit__.Application
        except Exception:
            try:
                from pyrevit import HOST_APP
                app = HOST_APP.app
            except Exception:
                app = None

    if app is None:
        meta = _empty_meta(path)
        meta["error"] = u"no_application"
        return meta

    doc = None
    try:
        opts = OpenOptions()
        try:
            opts.Audit = False
        except Exception:
            pass
        model_path = ModelPathUtils.ConvertUserVisiblePathToModelPath(path)
        doc = app.OpenDocumentFile(model_path, opts)
        if doc is None:
            meta = _empty_meta(path)
            meta["error"] = u"open_failed"
            return meta
        meta = _inspect_document(doc, path)
    except Exception as ex:
        meta = _empty_meta(path)
        meta["error"] = _u(ex)
        avro_log.write("family_inspect.fail", u"{}: {}".format(path, meta["error"]))
    finally:
        if doc is not None:
            try:
                doc.Close(False)
            except Exception as ex:
                avro_log.exception("family_inspect.close", ex)

    if meta.get("ok"):
        save_cached(path, meta)
    return meta


_UNSET = object()


def build_meta_by_path(families_or_paths):
    """Return dict mapping path -> cached meta dict (or None)."""
    meta_by_path = {}
    if not families_or_paths:
        return meta_by_path
    for item in families_or_paths:
        if isinstance(item, basestring):
            p = item
        elif isinstance(item, dict):
            p = item.get("path") or u""
        else:
            p = getattr(item, "path", None) or getattr(item, "Path", None) or u""
        if p and p not in meta_by_path:
            meta_by_path[p] = load_cached(p)
    return meta_by_path


def hosting_of(rfa_path, cached_meta=_UNSET):
    """Cached hosting key or HOST_UNKNOWN."""
    if cached_meta is _UNSET:
        cached = load_cached(rfa_path) if rfa_path else None
    else:
        cached = cached_meta
    if cached and cached.get("ok"):
        return cached.get("hosting") or HOST_UNKNOWN
    return HOST_UNKNOWN


def category_of(fi_or_path, cached_meta=_UNSET):
    """Revit category for filter axis (from cached inspector metadata)."""
    if fi_or_path is None:
        return u""

    path = u""
    if not isinstance(fi_or_path, basestring):
        path = getattr(fi_or_path, "path", None) or getattr(
            fi_or_path, "Path", None) or u""
    else:
        path = fi_or_path

    if cached_meta is _UNSET:
        cached = load_cached(path) if path else None
    else:
        cached = cached_meta
    if cached and cached.get("ok"):
        cat = _u(cached.get("category") or u"").strip()
        if cat:
            return cat

    if not isinstance(fi_or_path, basestring):
        scanned = _u(getattr(fi_or_path, "category", None) or u"").strip()
        if scanned:
            return scanned

    return u""


def placement_of(fi_or_path, cached_meta=_UNSET):
    """Placement type string from FamilyInfo / cache."""
    if fi_or_path is None:
        return u""
    path = u""
    guessed = u""
    if not isinstance(fi_or_path, basestring):
        guessed = _u(
            getattr(fi_or_path, "placement", None)
            or getattr(fi_or_path, "Placement", None)
            or u""
        ).strip()
        path = getattr(fi_or_path, "path", None) or getattr(
            fi_or_path, "Path", None) or u""
    else:
        path = fi_or_path
    if cached_meta is _UNSET:
        cached = load_cached(path) if path else None
    else:
        cached = cached_meta
    if cached and cached.get("ok"):
        pl = _u(cached.get("placement") or u"").strip()
        if pl:
            return pl
    return guessed


def _bool_filter_key(value):
    if isinstance(value, basestring):
        v = _u(value).strip().lower()
        if v in (BOOL_YES, u"true", u"1"):
            return BOOL_YES
        if v in (BOOL_NO, u"false", u"0"):
            return BOOL_NO
        if v == BOOL_UNKNOWN:
            return BOOL_UNKNOWN
        return BOOL_UNKNOWN
    if value is None:
        return BOOL_UNKNOWN
    try:
        return BOOL_YES if bool(value) else BOOL_NO
    except Exception:
        return BOOL_UNKNOWN


def _cached_bool_key(path, key, cached_meta=_UNSET):
    """Return tri-state bool key from cache: yes/no/unknown."""
    if cached_meta is _UNSET:
        if not path:
            return BOOL_UNKNOWN
        cached = load_cached(path)
    else:
        cached = cached_meta
    if not cached or not cached.get("ok"):
        return BOOL_UNKNOWN
    if key not in cached:
        return BOOL_UNKNOWN
    try:
        return _bool_filter_key(cached.get(key))
    except Exception:
        return BOOL_UNKNOWN


def revit_format_of(fi_or_path, cached_meta=_UNSET):
    """Stable Revit version label (R22/R24) from cache or scanner fallback."""
    if fi_or_path is None:
        return u""
    if isinstance(fi_or_path, basestring):
        path = fi_or_path
        guessed = u""
    else:
        path = getattr(fi_or_path, "path", None) or getattr(fi_or_path, "Path", None) or u""
        guessed = _u(getattr(fi_or_path, "revit_version", u"") or u"").strip()
    if cached_meta is _UNSET:
        cached = load_cached(path) if path else None
    else:
        cached = cached_meta
    if cached and cached.get("ok"):
        lab = normalize_revit_label(cached.get("revit_format") or u"")
        if lab:
            return lab
    return normalize_revit_label(guessed)


def is_shared_family_of_fi(fi, cached_meta=_UNSET):
    if fi is None:
        return BOOL_UNKNOWN
    path = getattr(fi, "path", None) or getattr(fi, "Path", None) or u""
    return _cached_bool_key(path, "is_shared_family", cached_meta=cached_meta)


def has_imported_geometry_of_fi(fi, cached_meta=_UNSET):
    if fi is None:
        return BOOL_UNKNOWN
    path = getattr(fi, "path", None) or getattr(fi, "Path", None) or u""
    return _cached_bool_key(path, "has_imported_geometry", cached_meta=cached_meta)


def has_shared_nested_of_fi(fi, cached_meta=_UNSET):
    if fi is None:
        return BOOL_UNKNOWN
    path = getattr(fi, "path", None) or getattr(fi, "Path", None) or u""
    return _cached_bool_key(path, "has_shared_nested", cached_meta=cached_meta)


def always_vertical_of_fi(fi, cached_meta=_UNSET):
    if fi is None:
        return BOOL_UNKNOWN
    path = getattr(fi, "path", None) or getattr(fi, "Path", None) or u""
    return _cached_bool_key(path, "always_vertical", cached_meta=cached_meta)


def work_plane_based_of_fi(fi, cached_meta=_UNSET):
    """Return tri-state from cache; fallback to placement-derived guess."""
    if fi is None:
        return BOOL_UNKNOWN
    path = getattr(fi, "path", None) or getattr(fi, "Path", None) or u""
    key = _cached_bool_key(path, "work_plane_based", cached_meta=cached_meta)
    if key != BOOL_UNKNOWN:
        return key
    pl = placement_of(fi, cached_meta=cached_meta)
    try:
        pl = (pl or u"").lower()
    except Exception:
        pl = u""
    if not pl:
        return BOOL_UNKNOWN
    if u"workplane" in pl or u"work plane" in pl or u"work_plane" in pl:
        return BOOL_YES
    return BOOL_NO


def hosting_of_fi(fi, cached_meta=_UNSET):
    if fi is None:
        return HOST_UNKNOWN
    host = getattr(fi, "hosting", None) or getattr(fi, "Hosting", None)
    if host:
        return _u(host)
    path = getattr(fi, "path", None) or getattr(fi, "Path", u"")
    return hosting_of(path, cached_meta=cached_meta)


def filter_families(
    families,
    category=None, hosting=None, placement=None,
    revit_format=None,
    has_imported_geometry=None,
    has_shared_nested=None,
    is_shared_family=None,
    work_plane_based=None,
    always_vertical=None,
    meta_by_path=None,
):
    """
    Filter by category / hosting / placement.

    Each argument may be:
      - None / '' / 'all' / empty list/set → no filter on that axis
      - string → single value
      - list/tuple/set of strings → match any (OR within axis)

    Axes are combined with AND.
    """
    cat_keys = _normalize_filter_keys(category)
    host_keys = set(k.lower() for k in _normalize_filter_keys(hosting))
    place_keys = set(k.lower() for k in _normalize_filter_keys(placement))

    ver_keys = set(k.lower() for k in _normalize_filter_keys(revit_format))
    imp_keys = set(k.lower() for k in _normalize_filter_keys(has_imported_geometry))
    shared_nested_keys = set(k.lower() for k in _normalize_filter_keys(has_shared_nested))
    shared_family_keys = set(k.lower() for k in _normalize_filter_keys(is_shared_family))
    wp_keys = set(k.lower() for k in _normalize_filter_keys(work_plane_based))
    av_keys = set(k.lower() for k in _normalize_filter_keys(always_vertical))

    use_cat = bool(cat_keys)
    use_host = bool(host_keys)
    use_place = bool(place_keys)
    use_ver = bool(ver_keys)
    use_imp = bool(imp_keys)
    use_sn = bool(shared_nested_keys)
    use_sf = bool(shared_family_keys)
    use_wp = bool(wp_keys)
    use_av = bool(av_keys)

    if not (use_cat or use_host or use_place or use_ver or use_imp or use_sn or use_sf or use_wp or use_av):
        return list(families or [])

    cat_lower = set(k.lower() for k in cat_keys)
    out = []
    for fi in families or []:
        path = getattr(fi, "path", None) or getattr(fi, "Path", None) or u""
        meta = meta_by_path.get(path) if (meta_by_path is not None and path) else _UNSET
        if use_cat:
            if category_of(fi, cached_meta=meta).lower() not in cat_lower:
                continue
        if use_host:
            if hosting_of_fi(fi, cached_meta=meta).lower() not in host_keys:
                continue
        if use_place:
            if placement_of(fi, cached_meta=meta).lower() not in place_keys:
                continue

        if use_ver:
            if revit_format_of(fi, cached_meta=meta).lower() not in ver_keys:
                continue
        if use_imp:
            if has_imported_geometry_of_fi(fi, cached_meta=meta).lower() not in imp_keys:
                continue
        if use_sn:
            if has_shared_nested_of_fi(fi, cached_meta=meta).lower() not in shared_nested_keys:
                continue
        if use_sf:
            if is_shared_family_of_fi(fi, cached_meta=meta).lower() not in shared_family_keys:
                continue
        if use_wp:
            if work_plane_based_of_fi(fi, cached_meta=meta).lower() not in wp_keys:
                continue
        if use_av:
            if always_vertical_of_fi(fi, cached_meta=meta).lower() not in av_keys:
                continue
        out.append(fi)
    return out


def _normalize_filter_keys(value):
    """Return list of filter keys; empty means 'no filter'."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        keys = []
        for v in value:
            k = _u(v).strip()
            if k and k.lower() != HOST_ALL:
                keys.append(k)
        return keys
    k = _u(value).strip()
    if not k or k.lower() == HOST_ALL:
        return []
    return [k]


def filter_by_host(families, host_key):
    """Backward-compatible host-only filter."""
    return filter_families(families, hosting=host_key)


def collect_filter_options(families, meta_by_path=None):
    """
    Collect distinct category / hosting / placement / version values for scope.
    Version labels always normalized (R22/R24). Scanner revit_version is used
    when inspect cache is missing so the Version filter is not empty.
    """
    categories = set()
    hostings = set()
    placements = set()

    revit_formats = set()
    has_imported_geometry = set()
    has_shared_nested = set()
    is_shared_family = set()
    work_plane_based = set()
    always_vertical = set()
    for fi in families or []:
        path = getattr(fi, "path", None) or getattr(fi, "Path", None) or u""
        if meta_by_path is not None:
            cached = meta_by_path.get(path) if path else None
        else:
            cached = load_cached(path) if path else None

        cat = category_of(fi, cached_meta=cached)
        if cat:
            categories.add(cat)

        # Version: always collect stable label (cache and/or scanner)
        ver = revit_format_of(fi, cached_meta=cached)
        if ver:
            revit_formats.add(ver)

        if cached and cached.get("ok"):
            host = _u(cached.get("hosting") or HOST_UNKNOWN).strip() or HOST_UNKNOWN
            hostings.add(host)
            pl = _u(cached.get("placement") or u"").strip()
            if pl:
                placements.add(pl)

            try:
                has_imported_geometry.add(_bool_filter_key(cached.get("has_imported_geometry")))
            except Exception:
                pass
            try:
                has_shared_nested.add(_bool_filter_key(cached.get("has_shared_nested")))
            except Exception:
                pass
            try:
                is_shared_family.add(_bool_filter_key(cached.get("is_shared_family")))
            except Exception:
                pass
            try:
                work_plane_based.add(_bool_filter_key(cached.get("work_plane_based")))
            except Exception:
                pass
            try:
                always_vertical.add(_bool_filter_key(cached.get("always_vertical")))
            except Exception:
                pass
            continue

        host = hosting_of_fi(fi, cached_meta=cached)
        if host and host != HOST_UNKNOWN:
            hostings.add(host)
        pl = placement_of(fi, cached_meta=cached)
        if pl:
            placements.add(pl)

    return {
        "categories": sorted(categories, key=lambda s: s.lower()),
        "hostings": sorted(hostings, key=lambda s: s.lower()),
        "placements": sorted(placements, key=lambda s: s.lower()),
        "revit_formats": sorted(revit_formats, key=lambda s: s.lower()),
        "has_imported_geometry": sorted(has_imported_geometry, key=lambda s: s.lower()),
        "has_shared_nested": sorted(has_shared_nested, key=lambda s: s.lower()),
        "is_shared_family": sorted(is_shared_family, key=lambda s: s.lower()),
        "work_plane_based": sorted(work_plane_based, key=lambda s: s.lower()),
        "always_vertical": sorted(always_vertical, key=lambda s: s.lower()),
    }


# Known FamilyPlacementType values (Revit API) for stable labels
PLACEMENT_KEYS = (
    u"OneLevelBased",
    u"OneLevelBasedHosted",
    u"TwoLevelsBased",
    u"ViewBased",
    u"WorkPlaneBased",
    u"CurveBased",
    u"CurveBasedDetail",
    u"CurveDrivenStructural",
    u"Adaptive",
    u"Invalid",
)
