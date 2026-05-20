# -*- coding: utf-8 -*-
"""
Family scanner for AVRO pyRevit extension.

Walks library directories and returns FamilyInfo objects.
Preview images are extracted from .rfa files using Revit API when possible.
"""
import os
import sys
import re

import rfa_version

# Revit API available when running inside pyRevit
try:
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit.DB import (
        Document, Family, FamilySymbol, OpenOptions,
        TransmissionData, ModelPath, FilePath,
    )
    REVIT_AVAILABLE = True
except Exception:
    REVIT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------
class FamilyInfo(object):
    """Lightweight descriptor for a single .rfa file."""

    __slots__ = (
        "name",         # display name (no extension)
        "path",         # absolute path to .rfa
        "category",     # guessed category string (search)
        "size_kb",      # file size
        "modified",     # modification timestamp string
        "preview",      # BitmapSource (if extracted), else None
        "folder",       # parent folder name
        "library_root", # root library path this file belongs to
        "rel_path",     # folder path relative to library_root
        "revit_version",  # R22, R24, …
    )

    def __init__(self, path, library_root=None):
        self.path     = path
        self.name     = os.path.splitext(os.path.basename(path))[0]
        self.folder   = os.path.basename(os.path.dirname(path))
        self.library_root = library_root or ""
        if self.library_root:
            try:
                rel = os.path.relpath(os.path.dirname(path), self.library_root)
                self.rel_path = u"" if rel == u"." else rel
            except Exception:
                self.rel_path = self.folder
        else:
            self.rel_path = self.folder
        self.category = _guess_category(path)
        self.preview  = None  # populated lazily
        stat          = os.stat(path)
        self.size_kb  = int(stat.st_size / 1024)
        import datetime
        self.modified = datetime.datetime.fromtimestamp(
            stat.st_mtime).strftime("%Y-%m-%d")
        self.revit_version = rfa_version.revit_version_label(path)

    def __repr__(self):
        return "<FamilyInfo '{}' cat='{}'>".format(self.name, self.category)


# ---------------------------------------------------------------------------
# Category guessing from path / filename heuristics
# ---------------------------------------------------------------------------
_CAT_KEYWORDS = [
    ("Furniture",           ["furniture", "chair", "table", "desk", "bed", "sofa",
                             "cabinet", "shelv", "shelf", "wardrobe"]),
    ("Doors",               ["door", "entry", "entree", "porta"]),
    ("Windows",             ["window", "fenetre", "glazing"]),
    ("Structural Columns",  ["column", "pillar", "col_"]),
    ("Structural Framing",  ["beam", "framing", "girder"]),
    ("Plumbing Fixtures",   ["toilet", "sink", "basin", "bath", "shower",
                             "lavatory", "plumb"]),
    ("Lighting Fixtures",   ["light", "lamp", "luminaire", "fixture_l"]),
    ("Electrical Fixtures", ["outlet", "switch", "panel", "electric"]),
    ("Mechanical Equipment",["ahu", "fcu", "boiler", "chiller", "hvac", "mech"]),
    ("Air Terminals",       ["diffuser", "grille", "air_term", "supply"]),
    ("Duct Fittings",       ["duct", "elbow_d", "tee_d"]),
    ("Pipe Fittings",       ["pipe", "elbow_p", "tee_p", "valve"]),
    ("Specialty Equipment", ["equip", "server", "rack", "vending"]),
    ("Casework",            ["casework", "kitchen", "counter"]),
    ("Parking",             ["parking", "car_"]),
    ("Site",                ["tree", "plant", "site", "bench", "fence"]),
    ("Stairs",              ["stair", "step", "riser"]),
    ("Railings",            ["railing", "baluster", "handrail"]),
    ("Curtain Panels",      ["curtain", "panel_cw", "cladding"]),
    ("Generic Models",      ["generic", "model_"]),
]


def _guess_category(rfa_path):
    """Guess Revit category from path segments and filename."""
    tokens = re.split(r"[\\/_ \-]", rfa_path.lower())
    for cat, keywords in _CAT_KEYWORDS:
        for kw in keywords:
            if any(kw in t for t in tokens):
                return cat
    # check parent folders
    parts = rfa_path.lower().replace("\\", "/").split("/")
    for cat, keywords in _CAT_KEYWORDS:
        for kw in keywords:
            if any(kw in p for p in parts):
                return cat
    return "Generic Models"


# ---------------------------------------------------------------------------
# Folder tree (library directory structure)
# ---------------------------------------------------------------------------
class FolderNode(object):
    """One folder in the library; children mirror disk structure."""

    __slots__ = ("path", "name", "children", "families")

    def __init__(self, path, name=None):
        self.path = os.path.normpath(os.path.abspath(path))
        self.name = name or os.path.basename(self.path) or self.path
        self.children = {}
        self.families = []

    def child(self, folder_path):
        name = os.path.basename(folder_path)
        if name not in self.children:
            self.children[name] = FolderNode(folder_path, name)
        return self.children[name]

    def descendants(self):
        result = list(self.families)
        for node in self.children.values():
            result.extend(node.descendants())
        return result

    def count(self):
        return len(self.descendants())


def _node_for_dir(nodes, library_root, dirpath):
    dirpath = os.path.normpath(os.path.abspath(dirpath))
    library_root = os.path.normpath(os.path.abspath(library_root))
    if dirpath in nodes:
        return nodes[dirpath]
    if dirpath == library_root:
        return nodes[library_root]
    parent_path = os.path.dirname(dirpath)
    parent = _node_for_dir(nodes, library_root, parent_path)
    return parent.child(dirpath)


def _prune_empty(node):
    remove = []
    for name, child in node.children.items():
        _prune_empty(child)
        if not child.families and not child.children:
            remove.append(name)
    for name in remove:
        del node.children[name]


def index_folder_tree(roots):
    """Map absolute folder path -> FolderNode."""
    index = {}

    def walk(node):
        index[node.path] = node
        for child in node.children.values():
            walk(child)

    for root in roots:
        walk(root)
    return index


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------
def scan_library(root_paths, progress_cb=None):
    """
    Walk root_paths recursively; build folder tree + flat family list.

    Returns:
        dict with keys:
          roots  - list of FolderNode (one per library path)
          all    - flat list of FamilyInfo
          index  - path -> FolderNode
    """
    roots = []
    all_families = []
    total = 0

    for root in root_paths:
        if not os.path.isdir(root):
            continue
        library_root = os.path.normpath(os.path.abspath(root))
        root_node = FolderNode(library_root)
        nodes = {library_root: root_node}

        for dirpath, _dirs, files in os.walk(library_root):
            node = _node_for_dir(nodes, library_root, dirpath)
            for fname in files:
                if not fname.lower().endswith(".rfa"):
                    continue
                fpath = os.path.join(dirpath, fname)
                try:
                    fi = FamilyInfo(fpath, library_root=library_root)
                    node.families.append(fi)
                    all_families.append(fi)
                    total += 1
                    if progress_cb and total % 20 == 0:
                        progress_cb(total)
                except Exception:
                    pass

        _prune_empty(root_node)
        for node in nodes.values():
            node.families.sort(key=lambda f: f.name.lower())
        roots.append(root_node)

    all_families.sort(key=lambda f: f.name.lower())
    return {
        "roots": roots,
        "all": all_families,
        "index": index_folder_tree(roots),
    }


def flat_search(all_families, query):
    """
    Return flat list of FamilyInfo matching query string.

    Args:
        all_families: list from scan_library()["all"]
        query:        str search term (case-insensitive)

    Returns:
        list of FamilyInfo
    """
    q = query.lower().strip()
    if not q:
        return []
    results = []
    for fi in all_families:
        hay = u" ".join([
            fi.name.lower(),
            fi.category.lower(),
            fi.folder.lower(),
            (fi.rel_path or u"").lower().replace("\\", " ").replace("/", " "),
            (getattr(fi, "revit_version", u"") or u"").lower(),
        ])
        if q in hay:
            results.append(fi)
    results.sort(key=lambda f: f.name.lower())
    return results


# ---------------------------------------------------------------------------
# Preview extraction (embedded PNG in .rfa compound file)
# ---------------------------------------------------------------------------
def extract_preview_png_bytes(rfa_path):
    """Return raw PNG bytes from an .rfa preview stream, or None."""
    try:
        import rfa_preview
        return rfa_preview.extract_preview_png_bytes(rfa_path)
    except Exception:
        return None


def extract_preview(app, rfa_path):
    """Legacy alias; returns PNG bytes (not BitmapSource)."""
    return extract_preview_png_bytes(rfa_path)
