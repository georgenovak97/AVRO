# AVRO — agent notes (pyRevit / Revit)

Python-only pyRevit extension (Family Browser and related tools). No new C# unless there is an ADR and a measured hotspot. See `docs/adr/0001-python-only.md`.

OpenCode models stay as configured in `opencode.json` (OpenRouter). Do not switch providers.

## Target Revit versions

| Year | Status |
|------|--------|
| 2020 | oldest supported — smoke before release |
| 2021 | supported |
| 2022 | supported |
| 2023 | supported |
| 2024 | supported (dark UI, API deprecations) |
| 2025 | newest supported in ADR |
| 2026+ | untested — do not assume it works |

Runtime: **pyRevit 4.8+**, **IronPython 2.7** inside Revit. Unit tests run on **CPython 3** with shims (`unicode = str`) on a machine without Revit, so anything requiring a live Revit session cannot be verified there.

API that differs by year (guard or dual-path):

- `ElementId.IntegerValue` → `.Value` on newer APIs (keep a fallback).
- `inst.Symbol` → `GetFamilySymbol()` where required.
- Transactions and `IExternalEventHandler` only on the Revit API thread.

## Layout

- `AVRO.tab/**/script.py` — ribbon entry (WPF + Revit API).
- `lib/` — shared helpers (`revit_utils.py` for IronPython quirks).
- `startup.py` — pyRevit session start.
- `tests/` — CPython unit tests (no Revit).
- `scripts/check.py` — local gate (structure + tests + ruff + `git diff --check`).

This repo is normally checked out as `AVRO/` inside a parent workspace. Commit in the **AVRO** git remote, not the parent workspace repo.

## IronPython 2.7 (Revit-side code)

In `lib/`, `startup.py`, and `AVRO.tab/**`:

- No f-strings, walrus, `match`, type annotations, or `async`.
- Keep `from __future__ import print_function` where `print` is used.
- Prefer `u"..."` and `as_unicode()` from `revit_utils`.
- `unicode` / `basestring` / `clr` / `System` / `Autodesk` are normal; tests shim `unicode`.
- Do not run pyupgrade / ruff `UP*` fixes on this tree.

## Revit transactions

Load skill `revit-api-transactions` when changing the model.

- Read-only collectors: no transaction.
- One user action → one named `Transaction` / `TransactionGroup` (`Transaction(doc, "AVRO: …")`).
- `Start` → work → `Commit`; on failure `RollBack`. Never leave a started transaction.
- No nested `Start` without a group. Prefer a single rollback path.
- Do not swallow `OperationCanceledException`.
- Model writes: `ExternalEvent` / Idling on the API thread, never a worker thread.

## Checks

From `AVRO/`:

```bash
python3 scripts/check.py
# or
~/.local/bin/ruff check .
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Ruff is configured for IronPython-safe rules (no pyupgrade). Do not enable `UP` to “modernize” the extension.

## Review / release

- Subagent `code-reviewer`: read-only, Revit/pyRevit focus.
- Skills: `revit-api-transactions`, `avro-extension-commits`, `plugin-release-checklist`.
- Before a client build: changelog in human language, no secrets/absolute paths, smoke on Revit **2020** and **2025**.
