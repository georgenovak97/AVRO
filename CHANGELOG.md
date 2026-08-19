# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `docs/PLAN.md` — reviewed work plan grouped into batches, with the items that
  require a Revit machine separated from those verifiable without Revit.
- `AGENTS.md` — supported Revit years, IronPython 2.7 constraints, transaction
  rules and the local check gate.
- `pyproject.toml` — ruff configuration (E/F/W, pyupgrade disabled so the
  IronPython tree is not rewritten into py3-only syntax), now run by
  `scripts/check.py`.
- `.gitattributes` — keeps text files normalized to LF.

### Changed
- README: corrected the ribbon tab name to **AVRO**, narrowed the supported
  range to Revit 2020–2025, and reworded the filter list to match the current
  split between filter axes and constraints.
- `extension.json` repository URL.
- Significantly faster filter application and search refreshes on network
  libraries by batch-loading family inspection metadata and eliminating
  redundant network round-trips.
- Precomputed Revit version detection during background scanning, eliminating
  UI freezes when scrolling and populating family cards.

### Fixed
- README typo and outdated feature list.
- `README.md` and `extension.json` were the only CRLF files in an otherwise LF
  repository, which made `git diff --check` fail on every edit to them.
- Cyrillic Revit error and status messages no longer risk mojibake or encoding
  crashes under IronPython 2.7.
- Changes in library subfolders (e.g. adding or updating families) are now
  detected automatically without requiring a manual cache reload.
- Orphaned metadata and thumbnail cache files are now automatically pruned over
  time instead of accumulating on disk.
- Properties panel now immediately renders the loading state when inspecting
  uncached family files instead of appearing unresponsive.

### Removed
- Unused C# `AVRO.Core` project; the extension is now Python-only
  (see `docs/adr/0001-python-only.md`). Its stale `.gitignore` rules too.

## [1.2.1-dev] - 2026-08-12

### Changed
- Settings dialog shows `1.2.1-dev` to distinguish develop builds.
- Refactored shared IronPython helpers into `lib/revit_utils.py`.

## [1.2.0] - 2026-08-12

### Added
- Family Browser filters: category, hosting, placement, Revit version, imported geometry, shared nested, shared family.
- Family properties panel with types, parameters, and formulas.
- Family metadata inspection and caching.

### Removed
- Search tool and hotkey integration.
