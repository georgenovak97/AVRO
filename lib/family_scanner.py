# -*- coding: utf-8 -*-
"""
Family scanner for AVRO pyRevit extension.

Walks library directories and returns FamilyInfo objects.
Preview images are extracted from .rfa files using Revit API when possible.
"""
import os
import re

import rfa_version

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
        self.category = category_from_path(path, self.library_root)
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
# Category from library folder (primary) + keyword fallback
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


def category_from_path(rfa_path, library_root=None):
    """
    Category for browser filters = last folder under the library root
    (same rule as AVRO.Core). Falls back to keyword guess, then parent name.
    """
    try:
        dir_path = os.path.dirname(os.path.abspath(rfa_path or u""))
        root = (library_root or u"").strip()
        if root:
            root = os.path.abspath(root)
            rel = os.path.relpath(dir_path, root)
            if rel and rel != os.curdir and not rel.startswith(u".."):
                parts = rel.replace(u"\\", u"/").split(u"/")
                parts = [p for p in parts if p]
                if parts:
                    return parts[-1]
        parent = os.path.basename(dir_path)
        if parent:
            return parent
    except Exception:
        pass
    return _guess_category_keywords(rfa_path)


def _guess_category_keywords(rfa_path):
    """Keyword fallback: match whole path tokens only (no substring)."""
    tokens = set(re.split(r"[\\/_ \-]+", (rfa_path or u"").lower()))
    tokens.discard(u"")
    for cat, keywords in _CAT_KEYWORDS:
        for kw in keywords:
            if kw in tokens:
                return cat
    return u"Generic Models"


def _guess_category(rfa_path, library_root=None):
    """Backward-compatible alias."""
    return category_from_path(rfa_path, library_root)


# ---------------------------------------------------------------------------
# Folder tree (library directory structure)
# ---------------------------------------------------------------------------
class FolderNode(object):
    """One folder in the library; children mirror disk structure."""

    __slots__ = (
        "path", "name", "children", "families",
        "_desc_cache", "_count_cache",
    )

    def __init__(self, path, name=None):
        self.path = os.path.normpath(os.path.abspath(path))
        self.name = name or os.path.basename(self.path) or self.path
        self.children = {}
        self.families = []
        self._desc_cache = None
        self._count_cache = None

    def child(self, folder_path):
        name = os.path.basename(folder_path)
        if name not in self.children:
            self.children[name] = FolderNode(folder_path, name)
        return self.children[name]

    def descendants(self):
        cached = getattr(self, "_desc_cache", None)
        if cached is not None:
            return cached
        result = []
        stack = [self]
        while stack:
            node = stack.pop()
            result.extend(node.families)
            stack.extend(node.children.values())
        self._desc_cache = result
        return result

    def count(self):
        cached = getattr(self, "_count_cache", None)
        if cached is not None:
            return cached
        n = len(self.families)
        for child in self.children.values():
            n += child.count()
        self._count_cache = n
        return n


def finalize_folder_counts(roots):
    """Precompute subtree sizes once (avoids O(n^2) tree UI builds)."""

    def walk(node):
        n = len(node.families)
        for child in node.children.values():
            n += walk(child)
        node._count_cache = n
        return n

    for root in roots:
        walk(root)


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
            rfa_files = [fname for fname in files
                         if fname.lower().endswith(".rfa")]
            if not rfa_files:
                continue
            node = _node_for_dir(nodes, library_root, dirpath)
            nodes[os.path.normpath(os.path.abspath(dirpath))] = node
            for fname in rfa_files:
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
    finalize_folder_counts(roots)
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
        hay = fi.name.lower()
        if q in hay:
            results.append(fi)
    results.sort(key=lambda f: f.name.lower())
    return results
