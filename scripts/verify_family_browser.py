#!/usr/bin/env python3
"""Static smoke checks for Family Browser refactoring.

Runs without Revit, CLR or pyRevit. It validates source structure before a
commit reaches the Windows/Revit test loop.
"""
from __future__ import print_function

import ast
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENTRY_REL = os.path.join(
    "AVRO.tab", "02_Tools.panel", "FamilyBrowser.pushbutton", "script.py")
ENTRY = os.path.join(ROOT, ENTRY_REL)
LIB = os.path.join(ROOT, "lib")
REQUIRED_METHODS = {
    "_bind",
    "_init_window",
    "_load_selected",
    "show",
}


def fail(message):
    print("FAIL: " + message)
    return 1


def python_sources():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for filename in files:
            if filename.endswith(".py"):
                yield os.path.join(base, filename)


def parse_source(path):
    with open(path, "rb") as stream:
        source = stream.read()
    try:
        return ast.parse(source, filename=path)
    except SyntaxError as exc:
        raise RuntimeError("syntax error in {0}:{1}: {2}".format(
            os.path.relpath(path, ROOT), exc.lineno, exc.msg))


def find_dialog(tree):
    matches = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "FamilyBrowserDialog"
    ]
    if len(matches) != 1:
        raise RuntimeError(
            "expected exactly one FamilyBrowserDialog, found {0}".format(
                len(matches)))
    return matches[0]


def method_names(dialog):
    names = []
    for node in dialog.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
    return names


def direct_self_handler_refs(dialog):
    """Return direct self._on_* references used by += event bindings."""
    refs = set()
    for node in ast.walk(dialog):
        if not isinstance(node, ast.AugAssign) or not isinstance(node.op, ast.Add):
            continue
        value = node.value
        if (isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id == "self"
                and value.attr.startswith("_on_")):
            refs.add(value.attr)
    return refs


def local_family_browser_imports(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("family_browser_"):
                    names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("family_browser_"):
                names.add(node.module)
    return names


def has_entry_show_call(tree):
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "show"):
            return True
    return False


def main():
    errors = []

    for path in python_sources():
        try:
            parse_source(path)
        except RuntimeError as exc:
            errors.append(str(exc))

    if errors:
        for error in errors:
            fail(error)
        return 1

    tree = parse_source(ENTRY)
    dialog = find_dialog(tree)
    methods = method_names(dialog)
    method_set = set(methods)

    missing = sorted(REQUIRED_METHODS - method_set)
    if missing:
        errors.append("FamilyBrowserDialog missing methods: " + ", ".join(missing))

    duplicates = sorted(name for name in method_set if methods.count(name) > 1)
    if duplicates:
        errors.append("duplicate FamilyBrowserDialog methods: " + ", ".join(duplicates))

    missing_handlers = sorted(direct_self_handler_refs(dialog) - method_set)
    if missing_handlers:
        errors.append("event bindings reference missing methods: "
                      + ", ".join(missing_handlers))

    for module in sorted(local_family_browser_imports(tree)):
        path = os.path.join(LIB, module + ".py")
        if not os.path.isfile(path):
            errors.append("imported module is missing: lib/{0}.py".format(module))

    if not has_entry_show_call(tree):
        errors.append("entry point does not call FamilyBrowserDialog.show()")

    if errors:
        for error in errors:
            fail(error)
        return 1

    print("OK: {0} Python files parsed; FamilyBrowserDialog has {1} methods".format(
        sum(1 for _ in python_sources()), len(methods)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
