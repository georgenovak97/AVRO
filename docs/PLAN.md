# AVRO Extension — Plan

Full audit of `lib/` (24 modules), `scripts/`, `startup.py`, entry point
`AVRO.tab/02_Tools.panel/FamilyBrowser.pushbutton/script.py` (2461 lines).
Branch `main`, version `1.2.1-dev`.

Baseline verified: `ruff check .` clean, 45 unit tests pass.
Gate for every batch: `python3 scripts/check.py`.

Constraints that shape this plan:

- **ADR 0002** — `OpenDocumentFile`, `FilteredElementCollector`, `LoadFamily`,
  `Transaction`, and *any* `Autodesk.Revit.*` access are main-thread only.
  Any threading/lifecycle change requires a manual 20-cycle open/close Revit
  stress test plus a `git revert` rollback plan. **Not reproducible on the VPS.**
- **ADR 0003** — strict-unknown for quality flags: meta is usable only when
  `meta["ok"] is True`, and unknown must FAIL an active flag. Refactors must not
  silently turn strict into soft.
- **AGENTS.md** — IronPython 2.7 (no f-strings, annotations, walrus); smoke on
  Revit **2020 and 2025** before a client build.

---

## Batch 1 — Verifiable on the VPS (pure logic, no Revit needed)

| # | Commit | Files | What |
|---|--------|-------|------|
| 1 | `perf(filters): batch-load inspect meta per refresh` | `lib/family_inspector.py`, `script.py` | Build `meta_by_path` once per `_refresh_catalog_view` / `_rebuild_meta_filters`; add the parameter to `family_inspector.filter_families` and `collect_filter_options`. **Reuse the existing `family_browser_quality.filter_families(families, meta_by_path, flags, limits)` (`:215`) instead of the per-family `_apply_quality_flag_filters`.** Today roughly 5 `load_cached` calls per family in the filter plus 3 in `collect_filter_options`, and each `load_cached` runs `os.stat()` on the **network share** through `_cache_key` — that network round-trip is the dominant cost, not the local JSON read. Must preserve ADR 0003: a missing path yields `None`, which has to keep failing strictly. |
| 2 | `fix(cache): detect subfolder changes in library fingerprint` | `lib/library_cache.py` | `library_fingerprint` (`:152-163`) hashes only the *root* folder mtime, so families added inside subfolders on the share stay invisible until a manual Reload. Walk one or two levels of subdirectory mtimes, or sample per-file mtime into the meta file. |
| 3 | `fix(i18n): unicode-encode exception args in user messages` | `script.py:1299,2338` | `err=ex` → `err=as_unicode(ex)`, matching `:2091` and `:2290`. Cyrillic Revit messages currently risk mojibake under IronPython 2.7. |
| 4 | `fix(cache): prune orphaned family_meta entries` | `lib/family_inspector.py`, `lib/rfa_preview.py` | `_cache_key` is path + mtime (`:157-166`), so every external edit on the share orphans the previous `family_meta/*.json` permanently; only all-or-nothing `clear_cache()` exists. Add a size- or age-capped sweep on save. `rfa_preview.THUMB_CACHE_DIR` has the same pattern. |

---

## Batch 2 — Requires a Revit machine (ADR 0002 guardrails apply)

Do **not** merge from the VPS. Each item needs the full ADR 0002 checklist:
list of affected handlers, 20-cycle open/close stress test, revert plan.

| # | Commit | Files | What |
|---|--------|-------|------|
| 5 | `fix(ui): yield to dispatcher before blocking inspect` | `lib/family_browser_props.py`, `lib/family_inspector.py` | `props.inspect` (`:57-74`) calls `set_loading` and then `load_cached`/`inspect` on the same thread, so the "Reading .rfa…" hint never paints and the UI looks dead for 1-5 s. **Do not move `inspect` to a worker thread** — ADR 0002 forbids `OpenDocumentFile` off the main thread and `inspect:481` states the same. Yield a single dispatcher frame first, reusing the existing `_pump_ui_before_reopen` pattern (`script.py:2340-2362`). |
| 6 | `perf(cards): populate revit version without Revit API on scan thread` | `lib/family_browser_cards.py`, `lib/rfa_version.py`, `lib/family_scanner.py` | `make_card:111-114` calls `revit_version_label(fi.path)` on the UI thread whenever `fi.revit_version` is empty, reading up to 512 KB from the share. Precompute during the background scan using **only** `revit_version_from_path` and `_label_via_file_bytes`; `_label_via_basic_file_info` calls `BasicFileInfo.Extract`, which is Revit API and must stay on the main thread or be dropped. Decide explicitly which. |

---

## Batch 3 — Hygiene / minor (verifiable on the VPS)

| # | Commit | Files | What |
|---|--------|-------|------|
| 7 | `fix(api): dual-path deprecated ElementId and Symbol access` | `lib/family_inspector.py:346,350`, `script.py:2305` | `fid.IntegerValue` → `.Value` with fallback at **both** sites; `getattr(inst, "Symbol")` → `GetFamilySymbol()` first with `Symbol` as fallback. Required for Revit 2024+ per AGENTS.md. |
| 8 | `refactor(txn): single rollback path, recents after commit` | `script.py:2256-2280,2364-2399` | `_get_family_symbol` rolls back twice (`:2263`/`:2267`, then again at `:2277`); collapse to one path. `_load_families` calls `config.add_recent` (`:2383`) inside the open transaction, which takes `_IO_LOCK` and writes JSON to disk — move it after `Commit`. Consider `FailureHandlingOptions` for the batch path so a mid-batch family failure is not silent. |
| 9 | `chore: remove dead imports and unreachable branch` | `lib/family_scanner.py:15-24`, `lib/family_inspector.py:30`, `script.py:36-48`, `lib/library_cache.py:126-127` | Unused `REVIT_AVAILABLE` flag and RevitAPI imports in the pure-IO scanner, `Family as RevitFamily`, unused WPF/Revit imports in the entry script, duplicate `unicode` branch in `_utf8_to_unicode`. `pyproject.toml` currently ignores `F401` for exactly this reason — after the cleanup, tighten `per-file-ignores` so it cannot regress. |
| 10 | `perf: replace per-byte loops with managed decoding` | `lib/rfa_preview.py:324`, `lib/image_utils.py:43-44` | `"".join(chr(int(buf[i])) …)` and `buf[i] = ord(ch)` are O(n) IronPython loops over payloads up to ~1 MB. Use an `Encoding.GetEncoding("latin-1")` round-trip or `Marshal.Copy`. |
| 11 | `chore(version): single runtime source for version string` | `lib/config.py`, `settings_dialog.xaml`, `scripts/check.py` | Three sources exist today: `pyproject.toml:3`, the hardcoded `1.2.1-dev` in `settings_dialog.xaml:54`, and `CHANGELOG.md`. IronPython 2.7 cannot read TOML, so add a runtime `VERSION` constant, set the dialog text programmatically, and make `check.py` assert all three agree. `extension.json` stays untouched: pyRevit does not read a `version` key there — `ExtensionPackage.version` returns the git commit hash. |

---

## Batch 4 — Tests

| # | Commit | Files | What |
|---|--------|-------|------|
| 12 | `test(filters): cover filter_families and batch meta path` | `tests/test_family_inspector_filter.py` (new) | Fake `load_cached`; AND across axes; **ADR 0003 regression guard: missing meta must still fail an active quality flag after the Batch 1 refactor.** |
| 13 | `test(cache): cover fingerprint invalidation` | `tests/test_library_cache.py` (extend) | Fingerprint mismatch, stale-cache rejection, and the subfolder-mtime gap from item 2. |
| 14 | `test(loadopts): cover out-param fallback` | `tests/test_family_load_options.py` (new) | Mock `.Value` versus `__setitem__`; `FamilySource(0)`. This is the only module on the model-write path with zero coverage. |
| 15 | `test(preview): cover byte parsers` | `tests/test_rfa_preview.py` (new) | `_slice_png`, `_extract_jpeg_from_bytes`, `_maybe_inflate_truncated_gzip`, `_find_png_in_buffer` — pure Python, no CLR required. |

---

## Release

- `CHANGELOG.md` `[Unreleased]` written in human language, per the
  `plugin-release-checklist` skill.
- `python3 scripts/check.py` green after every batch.
- Before a client build: smoke on Revit **2020 and 2025**, readable `AVRO: …`
  transaction names in the Undo menu, no debug `TaskDialog`, no absolute paths,
  previous bundle still installable.

---

## Open findings (not scheduled)

- `reference_line_count` (`family_inspector.py:371-384`) relies on
  `getattr(rp, "IsReferenceLine", False)`, which has no public API backing, so
  the field is always `0`. `family_browser_quality.py:157-159` only consumes the
  **sum** with `reference_plane_count`, so the filter stays correct and only the
  standalone field is misleading. Tests hardcode the key, so do not delete it
  without updating `test_family_browser_quality.py`.
- The `reload_fixup` idling handler stays subscribed after a pyRevit reload, but
  it unsubscribes itself on its next tick (`:177`), so it self-heals. Nit.
- Transaction names resolve through i18n without an explicit `AVRO: ` prefix;
  adding one would make Undo entries attributable to the extension.
