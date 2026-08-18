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

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


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
