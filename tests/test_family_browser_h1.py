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
    def _source_tree(self):
        with open(SCRIPT, "r") as stream:
            return ast.parse(stream.read(), filename=SCRIPT)

    def test_restore_window_focus_computes_cache_total(self):
        tree = self._source_tree()

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

    def test_placement_flow_does_not_sleep_or_push_nested_dispatcher(self):
        tree = self._source_tree()
        names = [
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "time"
        ]
        self.assertNotIn("sleep", names)
        with open(SCRIPT, "r") as stream:
            source = stream.read()
        self.assertNotIn("Dispatcher.PushFrame", source)

    def test_reopen_has_loading_fallback_and_final_revit_activation(self):
        tree = self._source_tree()
        methods = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        with open(SCRIPT, "r") as stream:
            source = stream.read()
        reopen_source = ast.get_source_segment(
            source, methods["_restore_ui_after_reopen"])
        self.assertIn("_publish_pending_loads", reopen_source)
        show_source = ast.get_source_segment(
            source, methods["show"])
        self.assertIn("_activate_revit_window", show_source)

    def test_revit_activation_restores_only_minimized_window(self):
        tree = self._source_tree()
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_activate_revit_window"
        ]
        self.assertEqual(len(methods), 1)
        method = methods[0]
        iconic_calls = [
            node
            for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "IsIconic"
        ]
        restore_calls = [
            node
            for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "ShowWindow"
        ]
        self.assertEqual(len(iconic_calls), 1)
        self.assertEqual(len(restore_calls), 1)
        self.assertTrue(any(
            isinstance(parent, ast.If)
            and parent.test is iconic_calls[0]
            and restore_calls[0] in ast.walk(parent)
            for parent in ast.walk(method)
        ))

    def test_catalog_batches_are_limited_to_fifty(self):
        with open(SCRIPT, "r") as stream:
            source = stream.read()
        tree = ast.parse(source, filename=SCRIPT)
        values = {}
        for node in tree.body:
            if (isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id in (
                        "_CARD_UI_BATCH", "_CARD_UI_BATCH_THRESHOLD",
                        "_VIRTUAL_ITEM_LIMIT")):
                values[node.targets[0].id] = node.value
        for name in ("_CARD_UI_BATCH", "_CARD_UI_BATCH_THRESHOLD",
                     "_VIRTUAL_ITEM_LIMIT"):
            self.assertEqual(ast.literal_eval(values[name]), 50)

    def test_load_status_hides_already_loaded_count_when_new_families_loaded(self):
        with open(SCRIPT, "r") as stream:
            source = stream.read()
        tree = ast.parse(source, filename=SCRIPT)
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_load_families"
        ]
        self.assertEqual(len(methods), 1)
        skipped_conditions = [
            node.test
            for node in ast.walk(methods[0])
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.BoolOp)
            and isinstance(node.test.op, ast.And)
            and any(
                isinstance(value, ast.Name) and value.id == "skipped"
                for value in node.test.values)
        ]
        self.assertEqual(len(skipped_conditions), 1)
        self.assertTrue(any(
            isinstance(value, ast.UnaryOp)
            and isinstance(value.op, ast.Not)
            and isinstance(value.operand, ast.Name)
            and value.operand.id == "loaded"
            for value in skipped_conditions[0].values))

    def test_library_roots_are_expanded_but_nested_folders_are_collapsed(self):
        with open(SCRIPT, "r") as stream:
            source = stream.read()
        tree = ast.parse(source, filename=SCRIPT)
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_add_folder_node"
        ]
        self.assertEqual(len(methods), 1)
        expanded_assignments = [
            node
            for node in ast.walk(methods[0])
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Attribute)
                    and target.attr == "IsExpanded"
                    for target in node.targets)
        ]
        self.assertEqual(len(expanded_assignments), 1)
        value = expanded_assignments[0].value
        self.assertIsInstance(value, ast.Name)
        self.assertEqual(value.id, "is_root")


if __name__ == "__main__":
    unittest.main()
