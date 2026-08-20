# -*- coding: utf-8 -*-
import ast
import os
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(
    ROOT,
    "AVRO.tab",
    "02_Tools.panel",
    "FamilyBrowser.pushbutton",
    "script.py",
)


class FamilyBrowserH1Tests(unittest.TestCase):
    def test_restore_window_focus_computes_cache_total(self):
        with open(SCRIPT, "r") as stream:
            tree = ast.parse(stream.read(), filename=SCRIPT)

        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_restore_window_focus"
        ]
        self.assertEqual(len(methods), 1)

        total_assignments = [
            node
            for node in ast.walk(methods[0])
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "total"
                for target in node.targets
            )
        ]
        self.assertEqual(len(total_assignments), 1)

        value = total_assignments[0].value
        self.assertIsInstance(value, ast.Call)
        self.assertIsInstance(value.func, ast.Name)
        self.assertEqual(value.func.id, "len")


if __name__ == "__main__":
    unittest.main()
