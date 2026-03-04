"""
tf2_visualizer.layout — Hierarchical tree layout for the TF graph.

Implements a simplified Buchheim / Reingold-Tilford style layout that
produces (x, y) coordinates for each node arranged in a top-down tree.
Handles forests (multiple roots) by laying them out side-by-side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from tf2_visualizer.graph import FrameEdge


@dataclass
class LayoutNode:
    name: str
    x: float = 0.0
    y: float = 0.0
    children: List[LayoutNode] = field(default_factory=list)
    _mod: float = 0.0  # modifier for second pass


@dataclass
class GraphLayout:
    """Computed layout result."""
    nodes: Dict[str, Tuple[float, float]]  # name → (x, y)
    edges: List[Tuple[str, str, bool]]      # (parent, child, is_static)
    width: float
    height: float


# ── public entry point ─────────────────────────────────────────────

def compute_layout(
    edges: Dict[Tuple[str, str], FrameEdge],
    h_sep: float = 180.0,
    v_sep: float = 100.0,
) -> GraphLayout:
    """
    Compute a hierarchical layout for the TF forest.

    Parameters
    ----------
    edges : dict mapping (parent, child) → FrameEdge
    h_sep : horizontal distance between sibling nodes
    v_sep : vertical distance between tree levels
    """
    if not edges:
        return GraphLayout(nodes={}, edges=[], width=0, height=0)

    # Build adjacency
    children_map: Dict[str, List[str]] = {}
    parents_set: Set[str] = set()
    children_set: Set[str] = set()

    for (p, c) in edges:
        children_map.setdefault(p, []).append(c)
        parents_set.add(p)
        children_set.add(c)

    roots = sorted(parents_set - children_set)
    if not roots:
        # cycle — pick lexicographically first node as root
        roots = [sorted(parents_set | children_set)[0]]

    # Guard against cycles by tracking visited nodes
    visited: Set[str] = set()

    def build_tree(name: str) -> Optional[LayoutNode]:
        if name in visited:
            return None
        visited.add(name)
        node = LayoutNode(name=name)
        for child_name in sorted(children_map.get(name, [])):
            child_node = build_tree(child_name)
            if child_node is not None:
                node.children.append(child_node)
        return node

    trees = []
    for r in roots:
        t = build_tree(r)
        if t is not None:
            trees.append(t)

    # Also add orphan nodes that appear only as children with no further descendants
    all_in_trees = set(visited)
    all_nodes = parents_set | children_set
    for orphan in sorted(all_nodes - all_in_trees):
        trees.append(LayoutNode(name=orphan))

    # ── Reingold-Tilford simplified first pass ──────────────────

    def _first_pass(node: LayoutNode, depth: int = 0) -> None:
        node.y = depth
        if not node.children:
            node.x = 0
            return
        for child in node.children:
            _first_pass(child, depth + 1)
        if len(node.children) == 1:
            node.x = node.children[0].x
        else:
            left = node.children[0].x
            right = node.children[-1].x
            node.x = (left + right) / 2.0

        # Separate overlapping subtrees
        _fix_overlaps(node)

    def _fix_overlaps(node: LayoutNode) -> None:
        """Shift children subtrees so they don't overlap."""
        if len(node.children) < 2:
            return
        # collect right contour of left subtree vs left contour of right subtree
        for i in range(1, len(node.children)):
            left_tree = node.children[i - 1]
            right_tree = node.children[i]
            max_right = _rightmost(left_tree)
            min_left = _leftmost(right_tree)
            overlap = max_right - min_left + 1  # +1 unit gap
            if overlap > 0:
                _shift_tree(right_tree, overlap)
        # re-center parent
        left = node.children[0].x
        right = node.children[-1].x
        node.x = (left + right) / 2.0

    def _rightmost(node: LayoutNode) -> float:
        if not node.children:
            return node.x
        return max(node.x, max(_rightmost(c) for c in node.children))

    def _leftmost(node: LayoutNode) -> float:
        if not node.children:
            return node.x
        return min(node.x, min(_leftmost(c) for c in node.children))

    def _shift_tree(node: LayoutNode, dx: float) -> None:
        node.x += dx
        for c in node.children:
            _shift_tree(c, dx)

    for tree in trees:
        _first_pass(tree)

    # Lay out multiple trees side by side
    offset = 0.0
    for tree in trees:
        min_x = _leftmost(tree)
        shift = offset - min_x
        _shift_tree(tree, shift)
        offset = _rightmost(tree) + 2  # gap between trees

    # ── Collect positions ──────────────────────────────────────

    positions: Dict[str, Tuple[float, float]] = {}

    def _collect(node: LayoutNode) -> None:
        positions[node.name] = (node.x * h_sep, node.y * v_sep)
        for c in node.children:
            _collect(c)

    for tree in trees:
        _collect(tree)

    edge_list = [(e.parent, e.child, e.is_static) for e in edges.values()]

    max_x = max(p[0] for p in positions.values()) if positions else 0
    max_y = max(p[1] for p in positions.values()) if positions else 0

    return GraphLayout(
        nodes=positions,
        edges=edge_list,
        width=max_x,
        height=max_y,
    )
