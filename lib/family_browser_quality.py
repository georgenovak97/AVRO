# -*- coding: utf-8 -*-
"""
Quality / complexity filter engine for Family Browser.

Pure Python (no WPF / Revit UI). Safe for unit tests on CPython and
import from IronPython dialog code.

Policy (ADR 0003): STRICT unknown.
If a quality flag needs inspected metadata and cache is missing or not ok,
the family does NOT pass that active flag.
"""
from __future__ import print_function

# Flags that require family_meta cache (inspect).
META_REQUIRED_FLAGS = (
    "work_plane_only",
    "shared_only",
    "no_imported_cad",
    "limit_types",
    "limit_ref_planes",
    "limit_dimensions",
    "limit_nested",
    "limit_params",
    "limit_formulas",
    "limit_materials",
)

DEFAULT_LIMITS = {
    "limit_types": 10,
    "limit_ref_planes": 10,
    "limit_dimensions": 10,
    "limit_nested": 10,
    "limit_params": 10,
    "limit_formulas": 5,
    "limit_materials": 10,
    "not_huge": 5.0,
}


def is_meta_usable(meta):
    """True only when inspected cache exists and marked ok."""
    if not meta:
        return False
    try:
        return bool(meta.get("ok"))
    except Exception:
        return False


def any_flag_active(flags):
    if not flags:
        return False
    try:
        return any(bool(v) for v in flags.values())
    except Exception:
        return False


def _limit_value(limits, key, default):
    src = limits if limits is not None else {}
    try:
        if key == "not_huge":
            v = float(src.get(key, default))
            return 5.0 if v <= 0 else v
        v = int(src.get(key, default))
        return default if v < 1 else v
    except Exception:
        return default


def _meta_int(meta, key):
    """Return int from usable meta, or None if unknown."""
    if not is_meta_usable(meta):
        return None
    if key not in meta:
        return None
    try:
        val = meta.get(key)
        if val is None:
            return None
        return int(val)
    except Exception:
        return None


def _fi_size_kb(fi):
    if fi is None:
        return None
    if isinstance(fi, dict):
        raw = fi.get("size_kb", None)
    else:
        raw = getattr(fi, "size_kb", None)
    if raw is None:
        return None
    try:
        return float(raw)
    except Exception:
        return None


def passes_quality_flags(fi, meta, flags, limits=None):
    """
    Return True if family passes all active quality flags (AND).

    STRICT unknown:
    - active flag that needs meta + unusable meta -> False
    - not_huge uses filesystem size_kb on fi; missing size -> False when flag on
    """
    flags = flags or {}
    if not any_flag_active(flags):
        return True

    lim = DEFAULT_LIMITS.copy()
    if limits:
        try:
            lim.update(dict(limits))
        except Exception:
            pass

    # --- flags that need inspect cache ---
    if flags.get("work_plane_only"):
        if not is_meta_usable(meta):
            return False
        if not bool(meta.get("work_plane_based")):
            return False

    if flags.get("shared_only"):
        if not is_meta_usable(meta):
            return False
        if not bool(meta.get("is_shared_family")):
            return False

    if flags.get("no_imported_cad"):
        if not is_meta_usable(meta):
            return False
        if bool(meta.get("has_imported_geometry")):
            return False

    if flags.get("limit_types"):
        n = _meta_int(meta, "type_count")
        if n is None:
            return False
        if n > _limit_value(lim, "limit_types", 10):
            return False

    if flags.get("limit_ref_planes"):
        rp = _meta_int(meta, "reference_plane_count")
        rl = _meta_int(meta, "reference_line_count")
        if rp is None and rl is None:
            return False
        # missing one side counts as 0 only when meta usable and key absent→None
        # If meta usable but key missing, treat missing key as 0 for sum components
        # only when the other exists OR both keys can be 0 from inspect.
        if not is_meta_usable(meta):
            return False
        try:
            total = int(meta.get("reference_plane_count") or 0) + int(
                meta.get("reference_line_count") or 0
            )
        except Exception:
            return False
        if total > _limit_value(lim, "limit_ref_planes", 10):
            return False

    if flags.get("limit_dimensions"):
        n = _meta_int(meta, "dimension_count")
        if n is None:
            return False
        if n > _limit_value(lim, "limit_dimensions", 10):
            return False

    if flags.get("limit_nested"):
        n = _meta_int(meta, "nested_family_count")
        if n is None:
            return False
        if n > _limit_value(lim, "limit_nested", 10):
            return False

    if flags.get("limit_params"):
        n = _meta_int(meta, "param_total_count")
        if n is None:
            return False
        if n > _limit_value(lim, "limit_params", 10):
            return False

    if flags.get("limit_formulas"):
        n = _meta_int(meta, "param_has_formulas_count")
        if n is None:
            return False
        if n > _limit_value(lim, "limit_formulas", 5):
            return False

    if flags.get("limit_materials"):
        n = _meta_int(meta, "material_count")
        if n is None:
            return False
        if n > _limit_value(lim, "limit_materials", 10):
            return False

    # --- filesystem size (no inspect required) ---
    if flags.get("not_huge"):
        size_kb = _fi_size_kb(fi)
        if size_kb is None:
            return False
        try:
            max_kb = float(_limit_value(lim, "not_huge", 5.0)) * 1024.0
        except Exception:
            max_kb = 5.0 * 1024.0
        if size_kb > max_kb:
            return False

    return True


def filter_families(families, meta_by_path, flags, limits=None):
    """Filter iterable of family infos by quality flags. meta_by_path: path->meta."""
    if not any_flag_active(flags):
        return list(families or [])
    out = []
    meta_by_path = meta_by_path or {}
    for fi in families or []:
        if isinstance(fi, dict):
            path = fi.get("path") or u""
        else:
            path = getattr(fi, "path", None) or u""
        meta = meta_by_path.get(path) if path else None
        if passes_quality_flags(fi, meta, flags, limits=limits):
            out.append(fi)
    return out
