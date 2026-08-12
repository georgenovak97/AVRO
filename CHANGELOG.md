# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

## [Unreleased]

### Changed
- Removed unused C# `AVRO.Core` project; extension is now Python-only.
- Fixed `extension.json` repository URL.
- Fixed README typo and updated feature list.
