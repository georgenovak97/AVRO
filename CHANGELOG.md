# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `docs/PLAN.md` — reviewed work plan grouped into batches, with the items that
  require a Revit machine separated from those verifiable without Revit.

### Changed
- README: corrected the ribbon tab name to **AVRO**, narrowed the supported
  range to Revit 2020–2025, and reworded the filter list to match the current
  split between filter axes and constraints.
- `extension.json` repository URL.

### Fixed
- README typo and outdated feature list.

### Removed
- Unused C# `AVRO.Core` project; the extension is now Python-only
  (see `docs/adr/0001-python-only.md`).

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
