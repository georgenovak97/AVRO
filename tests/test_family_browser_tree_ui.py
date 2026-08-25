# -*- coding: utf-8 -*-
import ast
import os
import unittest
from xml.etree import ElementTree


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
XAML = os.path.join(
    ROOT, "AVRO.tab", "02_Tools.panel", "FamilyBrowser.pushbutton", "ui.xaml")
THEME = os.path.join(ROOT, "lib", "ui_theme.py")
NS = "{http://schemas.microsoft.com/winfx/2006/xaml/presentation}"


class FamilyBrowserTreeUiTests(unittest.TestCase):
    def test_tree_template_has_folder_icons_and_connectors(self):
        root = ElementTree.parse(XAML).getroot()
        resources = root.find(NS + "Window.Resources")
        self.assertIsNotNone(resources)
        keys = [node.attrib.get("{http://schemas.microsoft.com/winfx/2006/xaml}Key")
                for node in resources]
        self.assertIn("FolderIcon", keys)
        self.assertIn("HistoryIcon", keys)
        tree_style = next(node for node in resources
                          if node.tag == NS + "Style"
                          and node.attrib.get("TargetType") == "TreeViewItem")
        template = next(node for node in tree_style
                        if node.tag == NS + "Setter"
                        and node.attrib.get("Property") == "Template")
        template_text = ElementTree.tostring(template, encoding="unicode")
        self.assertIn("ToggleButton", template_text)
        self.assertIn("StrokeDashArray", template_text)
        self.assertIn("Expander", template_text)
        self.assertIn("Uid", template_text)
        self.assertIn("TreeLast", template_text)
        self.assertIn("ChildItems", template_text)
        self.assertIn('Visibility="Collapsed"', template_text)
        self.assertIn('TargetName="ChildItems"', template_text)
        self.assertIn('Value="Visible"', template_text)
        self.assertIn('Stretch="Uniform"', template_text)
        self.assertIn("BranchArm", template_text)
        self.assertIn('Value="TreeRecent"', template_text)
        self.assertIn('Width="20"', template_text)
        self.assertIn('Width="24"', template_text)
        all_text = ElementTree.tostring(root, encoding="unicode")
        self.assertIn("PlusVertical", all_text)

    def test_tree_theme_resources_exist_in_both_palettes(self):
        with open(THEME, "r") as stream:
            tree = ast.parse(stream.read(), filename=THEME)
        palettes = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id in ("LIGHT", "DARK"):
                    palettes[target.id] = ast.literal_eval(node.value)
        keys = ("TreeIcon", "TreeConnector")
        for palette in palettes.values():
            for key in keys:
                self.assertIn(key, palette)


if __name__ == "__main__":
    unittest.main()
