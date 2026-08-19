#!/usr/bin/env python3
"""Repository checks for AVRO refactor workflow.

Runs:
1) static Family Browser structure guard
2) ruff (E/F/W, IronPython-safe config in pyproject.toml)
3) unit tests
4) git diff whitespace sanity
"""
import os
import subprocess
import sys
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def check_version_consistency():
    """Ensure runtime, package metadata, and changelog use one version."""
    with open(os.path.join(ROOT, "pyproject.toml"), "r") as stream:
        pyproject = stream.read()
    with open(os.path.join(ROOT, "CHANGELOG.md"), "r") as stream:
        changelog = stream.read()
    pyproject_match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    changelog_match = re.search(r'^## \[([^\]]+)\] - ', changelog, re.M)
    if pyproject_match is None or changelog_match is None:
        print("FAIL: version source missing")
        return 1
    lib_path = os.path.join(ROOT, "lib")
    if lib_path not in sys.path:
        sys.path.insert(0, lib_path)
    import config
    versions = (config.VERSION, pyproject_match.group(1), changelog_match.group(1))
    if len(set(versions)) != 1:
        print("FAIL: version mismatch: " + ", ".join(versions))
        return 1
    return 0


def run(cmd):
    p = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print("$ " + " ".join(cmd))
    print(p.stdout.rstrip())
    return p.returncode


def ruff_cmd():
    local = os.path.expanduser("~/.local/bin/ruff")
    if os.path.isfile(local):
        return [local, "check", "."]
    return ["ruff", "check", "."]


def main():
    version_code = check_version_consistency()
    if version_code != 0:
        return version_code
    steps = [
        [sys.executable, "scripts/verify_family_browser.py"],
        ruff_cmd(),
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
        ["git", "diff", "--check"],
    ]
    for step in steps:
        code = run(step)
        if code != 0:
            return code
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
