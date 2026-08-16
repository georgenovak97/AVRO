# AVRO Extension — Plan

Full audit of `AVRO/lib/` (24 modules), `AVRO/scripts/`, `AVRO/startup.py`,
entry point `AVRO.tab/.../script.py`. Focus: Revit transactions, bugs/API
pitfalls, performance, tests/coverage. Branch: `main`, version: `1.2.1-dev`.

Sources: code review via `code-reviewer` subagent + manual file analysis.

---

## Batch 1 — UX-critical (1 PR: blockers + major)

| # | Commit | Files | What |
|----|--------|-------|------|
| 1 | `fix(filters): batch-load family meta on filter refresh` | `lib/family_inspector.py`, `AVRO.tab/.../script.py` | Add `meta_by_path` parameter to `filter_families` and `collect_filter_options`; load cache once per scope, not N× per family. Removes ~35k file opens on a 5k-family folder. |
| 2 | `fix(ui): defer family inspect off the UI thread` | `lib/family_browser_props.py`, `lib/family_inspector.py` | Move `inspect` to a one-shot Idling/ExternalEvent handler; "Reading .rfa…" hint now renders before the freeze. |
| 3 | `perf(cards): precompute revit version on scan thread` | `lib/family_browser_cards.py`, `lib/rfa_version.py`, `lib/family_scanner.py` | `fi.revit_version` populated during the background scan, not on the UI thread in `make_card`. |
| 4 | `fix(cache): detect subfolder changes in library fingerprint` | `lib/library_cache.py` | Walk 1-2 levels of subdirectory mtimes (or store per-file mtime in meta) so "Update" reliably detects external additions on network shares. |
| 5 | `fix(i18n): unicode-encode exception args in user messages` | `AVRO.tab/.../script.py:1299,2338` | `err=ex` → `err=as_unicode(ex)` (matches pattern already used at `:2290`). |

---

## Batch 2 — Refactor / minor fixes (1 PR: minor + nit)

| # | Commit | Files | What |
|----|--------|-------|------|
| 6 | `fix(inspect): guard against closing a user's already-open family doc` | `lib/family_inspector.py` | Before `OpenDocumentFile`, check `app.Documents` for the path; skip close or skip open if the user's family is already active. |
| 7 | `fix(api2024): replace deprecated IntegerValue and Symbol` | `lib/family_inspector.py:346,350` | `ElementId.IntegerValue` → `Value` (with fallback); `inst.Symbol` → `GetFamilySymbol()`. |
| 8 | `refactor(txn): single rollback path and post-commit recents` | `AVRO.tab/.../script.py` | Remove inner `RollBack` calls (let the single outer handler manage); move `add_recent` after `Commit`; optionally add `IsModifiable` guard. |
| 9 | `chore(dead): remove unused RevitAPI imports and flags` | `lib/family_scanner.py:15-24`, `lib/family_inspector.py:30`, `script.py:36-48`, `lib/library_cache.py:126-127` | Dead imports: `REVIT_AVAILABLE` flag, `Family as RevitFamily`, `BitmapImage/BitmapCacheOption/MemoryStream`, `RevitFamilySymbol/RevitElement`, `IFamilyLoadOptions` (provided by module), duplicate `_utf8_to_unicode` branch. |
| 10 | `fix(preview): dispose MemoryStream and use managed byte decoding` | `lib/image_utils.py:45-51`, `lib/rfa_preview.py:324` | Wrap `MemoryStream` in `try/finally Dispose()`; replace byte-by-byte `chr(int(...))` loop with `System.Text.Encoding.GetEncoding("latin-1").GetString`. |
| 11 | `fix(reload): retain idling handler across pyrevit reloads` | `lib/reload_fixup.py` | Store handler on a survivor object; `-=` on reload must reference the same object. |
| 12 | `chore(version): single source for version string` | `lib/config.py`, `settings_dialog.xaml.cs/.py`, `scripts/check.py` | `VERSION = "1.2.1-dev"` in `config.py`; dialog reads it programmatically; `check.py` validates against `CHANGELOG.md` header. `extension.json` intentionally left unchanged — pyRevit does not parse a `version` field there (it returns `last_commit_hash` from git instead). |

---

## Batch 3 — Tests (1 PR: high-value coverage gaps)

| # | Commit | Files | What |
|----|--------|-------|------|
| 14 | `test(filters): cover family_inspector.filter_families` | `tests/test_family_inspector_filter.py` (new) | Fake `load_cached`, AND/OR axis combinations, redundant-read regression. |
| 15 | `test(cache): cover fingerprint invalidation` | `tests/test_library_cache.py` (extend) | Fingerprint mismatch, stale rejection, subfolder-mtime gap. |
| 16 | `test(loadopts): cover family_load_options out-param fallback` | `tests/test_family_load_options.py` (new) | Mock `.Value`/`__setitem__` fallback, `FamilySource(0)` assignment. |
| 17 | `test(preview): cover byte parsers` | `tests/test_rfa_preview.py` (new) | `_slice_png`, `_extract_jpeg_from_bytes`, `_maybe_inflate_truncated_gzip`, `_find_png_in_buffer`. |

---

## Post-batches

- **CHANGELOG.md**: human-language summary in `[Unreleased]` (not a commit dump),
  per `plugin-release-checklist` skill.
- **Tests**: `python -m unittest discover tests` after each batch.
- **Before tag/release**: run `plugin-release-checklist` skill — smoke on oldest
  (Revit 2020) and newest supported, readable transaction names in Undo menu,
  no debug `TaskDialog`, no absolute paths, rollback path documented.

---

## Open findings (not planned, FYI)

- `reference_line_count` in `family_inspector.py:371-384` uses
  `getattr(rp, "IsReferenceLine", False)` which always falls back to `False`
  (property does not exist in public API). The field is always `0`. It is
  summed with `reference_plane_count` in `family_browser_quality.py:157-159`,
  so the quality filter is still correct — only the standalone field is
  misleading. Fix if `IsReferenceLine` becomes available, or document the
  limitation. Not blocking.
