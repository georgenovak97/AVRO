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

    def test_restore_window_focus_sets_done_status(self):
        tree = self._source_tree()

        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_restore_window_focus"
        ]
        self.assertEqual(len(methods), 1)

        with open(SCRIPT, "r") as stream:
            source = ast.get_source_segment(stream.read(), methods[0])
        self.assertIn('status_key="from_cache"', source)
        self.assertIn("i18n.t(status_key)", source)

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

    def test_reopen_has_loading_fallback_without_native_focus_workaround(self):
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
        self.assertNotIn("_activate_revit_window", show_source)

    def test_close_invalidates_background_work_and_guards_dispatch(self):
        tree = self._source_tree()
        methods = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        with open(SCRIPT, "r") as stream:
            source = stream.read()
        dispatch_source = ast.get_source_segment(
            source, methods["_dispatch_current_window"])
        cleanup_source = ast.get_source_segment(
            source, methods["_cleanup_window_resources"])
        preview_source = ast.get_source_segment(
            source, methods["_schedule_previews"])
        show_source = ast.get_source_segment(source, methods["show"])
        self.assertIn("_window_closing", dispatch_source)
        self.assertIn("_window_is_current", dispatch_source)
        self.assertIn("_preview_worker_lock", cleanup_source)
        self.assertIn("_scan_gen += 1", cleanup_source)
        self.assertIn("not self._window_closing", preview_source)
        self.assertIn("pending_request is not None", preview_source)
        self.assertIn("preview_thread.join", show_source)
        close_source = ast.get_source_segment(
            source, methods["_on_window_closing"])
        self.assertIn("saving_state", close_source)
        self.assertIn("e.Cancel = True", close_source)
        self.assertIn("on_done=self._close_after_save", close_source)
        self.assertIn("_allow_close_after_save", close_source)
        self.assertIn("not self._allow_close_after_save", close_source)
        self.assertIn("def _close_after_save", source)
        close_method = next(node for node in ast.walk(tree)
                            if isinstance(node, ast.FunctionDef)
                            and node.name == "_on_window_closing")
        cleanup_tries = [node for node in ast.walk(close_method)
                         if isinstance(node, ast.Try)
                         and any("_cleanup_window_resources" in ast.get_source_segment(
                             source, stmt) for stmt in node.finalbody)]
        self.assertEqual(len(cleanup_tries), 1)
        terminal_source = ast.get_source_segment(
            source, cleanup_tries[0])
        self.assertIn("self._window_closing = True", terminal_source)

    def test_close_disables_actions_and_has_save_timeout_fallback(self):
        with open(SCRIPT, "r") as stream:
            source = stream.read()
        tree = ast.parse(source, filename=SCRIPT)
        methods = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        close_source = ast.get_source_segment(
            source, methods["_on_window_closing"])
        place_source = ast.get_source_segment(
            source, methods["_place_family"])
        self.assertIn("FamilyScrollViewer.IsEnabled = False", close_source)
        self.assertIn("SearchBox.IsEnabled = False", close_source)
        self.assertIn('"BtnLoad"', close_source)
        self.assertIn("Dispatcher.BeginInvoke", close_source)
        self.assertIn("_close_after_save_timeout", close_source)
        self.assertIn("_close_requested", place_source)
        self.assertIn("_window_closing", place_source)

    def test_cleanup_cancels_close_timeout(self):
        with open(SCRIPT, "r") as stream:
            source = stream.read()
        tree = ast.parse(source, filename=SCRIPT)
        cleanup = next(node for node in ast.walk(tree)
                       if isinstance(node, ast.FunctionDef)
                       and node.name == "_cleanup_window_resources")
        cleanup_source = ast.get_source_segment(source, cleanup)
        self.assertIn("_cancel_close_timeout", cleanup_source)

    def test_batch_load_raises_window_without_overwriting_status(self):
        with open(SCRIPT, "r") as stream:
            source = stream.read()
        tree = ast.parse(source, filename=SCRIPT)
        methods = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        load_source = ast.get_source_segment(source, methods["_load_families"])
        focus_source = ast.get_source_segment(
            source, methods["_restore_window_focus"])
        self.assertIn("raise_window=True", load_source)
        self.assertIn("status_key=None", load_source)
        self.assertIn("Topmost", focus_source)

    def test_resize_during_catalog_change_is_replayed(self):
        with open(SCRIPT, "r") as stream:
            source = stream.read()
        tree = ast.parse(source, filename=SCRIPT)
        methods = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        schedule_source = ast.get_source_segment(
            source, methods["_schedule_grid_relayout"])
        debounce_source = ast.get_source_segment(
            source, methods["_on_grid_relayout_debounced"])
        finish_source = ast.get_source_segment(
            source, methods["_finish_family_view_layout"])
        self.assertIn("_grid_relayout_pending = True", schedule_source)
        self.assertIn("_grid_relayout_pending = True", debounce_source)
        self.assertIn("pending_relayout", finish_source)
        self.assertIn("_relayout_family_grid", finish_source)

    def test_saved_window_geometry_is_checked_against_available_screens(self):
        with open(SCRIPT, "r") as stream:
            source = stream.read()
        tree = ast.parse(source, filename=SCRIPT)
        methods = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        restore_source = ast.get_source_segment(
            source, methods["_restore_window_geometry"])
        visible_source = ast.get_source_segment(
            source, methods["_window_geometry_is_visible"])
        self.assertIn("_window_geometry_is_visible", restore_source)
        self.assertIn("CenterScreen", restore_source)
        self.assertIn("Screen.AllScreens", visible_source)
        self.assertIn("WorkingArea", visible_source)

    def test_busy_properties_inspection_does_not_disable_the_tree(self):
        props_path = os.path.join(ROOT, "lib", "family_browser_props.py")
        with open(props_path, "r") as stream:
            source = stream.read()
        tree = ast.parse(source, filename=props_path)
        begin = next(node for node in ast.walk(tree)
                     if isinstance(node, ast.FunctionDef)
                     and node.name == "begin_inspect")
        begin_source = ast.get_source_segment(source, begin)
        self.assertIn("Cursors.Wait", begin_source)
        self.assertNotIn("win.IsEnabled = False", begin_source)

    def test_right_click_defers_and_always_shows_properties_preparation(self):
        with open(SCRIPT, "r") as stream:
            source = stream.read()
        tree = ast.parse(source, filename=SCRIPT)
        method = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef)
                      and node.name == "_on_card_right_click")
        method_source = ast.get_source_segment(source, method)
        self.assertIn("begin_inspect", method_source)

        props_path = os.path.join(ROOT, "lib", "family_browser_props.py")
        with open(props_path, "r") as stream:
            props_source = stream.read()
        props_tree = ast.parse(props_source, filename=props_path)
        inspect = next(node for node in ast.walk(props_tree)
                       if isinstance(node, ast.FunctionDef)
                       and node.name == "inspect")
        inspect_source = ast.get_source_segment(props_source, inspect)
        begin = next(node for node in ast.walk(props_tree)
                     if isinstance(node, ast.FunctionDef)
                     and node.name == "begin_inspect")
        begin_source = ast.get_source_segment(props_source, begin)
        self.assertIn("self.set_loading(path)", inspect_source)
        self.assertIn("BeginInvoke", begin_source)
        self.assertIn("Topmost", begin_source)
        self.assertIn("Cursors.Wait", begin_source)
        self.assertIn("known_version", inspect_source)
        self.assertIn("_restore_after_inspect", begin_source)
        self.assertIn('reading_family', begin_source)
        self.assertIn('status_ready', source)

        set_loading = next(node for node in ast.walk(props_tree)
                           if isinstance(node, ast.FunctionDef)
                           and node.name == "set_loading")
        set_loading_source = ast.get_source_segment(
            props_source, set_loading)
        self.assertIn('hint.Text = u""', set_loading_source)
        self.assertIn("Visibility.Collapsed", set_loading_source)

        reset = next(node for node in ast.walk(props_tree)
                     if isinstance(node, ast.FunctionDef)
                     and node.name == "reset")
        reset_source = ast.get_source_segment(props_source, reset)
        self.assertIn("_show_help", reset_source)
        self.assertIn("Visibility.Visible", reset_source)

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

    def test_expander_click_does_not_open_catalog(self):
        with open(SCRIPT, "r") as stream:
            source = stream.read()
        tree = ast.parse(source, filename=SCRIPT)
        methods = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        selected_source = ast.get_source_segment(
            source, methods["_on_cat_selected"])
        bind_source = ast.get_source_segment(source, methods["_bind"])
        preview_source = ast.get_source_segment(
            source, methods["_on_tree_preview_mouse_down"])
        self.assertIn("_open_tree_item", selected_source)
        self.assertIn("PreviewMouseLeftButtonDown", bind_source)
        self.assertIn("IsExpanded", preview_source)
        self.assertIn("SelectedItem", preview_source)
        self.assertIn("_suppress_tree_events = True", preview_source)
        self.assertIn("selected.IsSelected = True", preview_source)
        self.assertIn("e.Handled", preview_source)
        self.assertNotIn("_expander_clicked", source)
        self.assertNotIn("MouseLeftButtonUp", bind_source)


if __name__ == "__main__":
    unittest.main()
