# -*- coding: utf-8 -*-
"""
Low-level WPF / XAML helpers used by AVRO dialogs.

Keeps XamlReader, visual-tree walking, and named-control resolution in one
place so dialog scripts stay focused on behaviour, not WPF plumbing.
"""
import codecs
import os

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows import FrameworkElement
from System.Windows.Markup import XamlReader
from System.Windows.Media import VisualTreeHelper


def load_xaml(directory, filename="ui.xaml"):
    """Load a XAML file from *directory* via ``XamlReader.Parse``."""
    xaml_path = os.path.join(directory, filename)
    with codecs.open(xaml_path, "r", "utf-8") as f:
        xaml_str = f.read()
    return XamlReader.Parse(xaml_str)


def find_named(root, name):
    """Look up a control by ``x:Name`` via ``FindName`` or visual-tree scan."""
    ctrl = root.FindName(name)
    if ctrl is not None:
        return ctrl
    return _find_in_visual_tree(root, name)


def _find_in_visual_tree(element, name):
    if element is None:
        return None
    if isinstance(element, FrameworkElement) and element.Name == name:
        return element
    count = VisualTreeHelper.GetChildrenCount(element)
    for i in range(count):
        child = VisualTreeHelper.GetChild(element, i)
        found = _find_in_visual_tree(child, name)
        if found is not None:
            return found
    return None


class NamedUiControls(object):
    """Resolve ``x:Name`` elements after ``XamlReader.Parse`` (no code-behind)."""

    def __init__(self, root, control_names):
        missing = []
        for name in control_names:
            ctrl = find_named(root, name)
            if ctrl is None:
                missing.append(name)
            else:
                setattr(self, name, ctrl)
        if missing:
            raise Exception(
                "Named controls not found in ui.xaml: " + ", ".join(missing))
