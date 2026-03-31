"""
tf2_visualizer_pkg.gui — Qt-based interactive TF tree viewer.

Uses QGraphicsView / QGraphicsScene for smooth pan & zoom, and a
QTimer to poll the TFGraph revision so the canvas repaints only when
the topology actually changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
)

from tf2_visualizer_pkg.graph import FrameEdge, TFGraph
from tf2_visualizer_pkg.layout import compute_layout

if TYPE_CHECKING:
    pass


# ── Colour palette ──────────────────────────────────────────────────

_CLR_BG = QColor("#1a1b26")
_CLR_NODE_FILL = QColor("#24283b")
_CLR_NODE_BORDER = QColor("#7aa2f7")
_CLR_NODE_STATIC_BORDER = QColor("#9ece6a")
_CLR_NODE_TEXT = QColor("#c0caf5")
_CLR_EDGE_DYNAMIC = QColor("#7aa2f7")
_CLR_EDGE_STATIC = QColor("#9ece6a")
_CLR_ROOT_GLOW = QColor("#bb9af7")
_CLR_STALE = QColor("#565f89")
_CLR_TOOLTIP_BG = QColor("#414868")
_CLR_STATUS_TEXT = QColor("#a9b1d6")

_NODE_PADDING_X = 18
_NODE_PADDING_Y = 10
_NODE_RADIUS = 8
_EDGE_WIDTH = 2.0
_ARROW_SIZE = 10

_FONT = QFont("Monospace", 10)
_FONT.setStyleHint(QFont.StyleHint.Monospace)
_FONT_BOLD = QFont("Monospace", 10, QFont.Weight.Bold)


# ── Custom Graphics Items ──────────────────────────────────────────


class NodeItem(QGraphicsRectItem):
    """Rounded-rect node representing a TF frame."""

    def __init__(
        self,
        name: str,
        x: float,
        y: float,
        is_root: bool = False,
        is_static_only: bool = False,
        edge_data: Optional[FrameEdge] = None,
    ) -> None:
        super().__init__()
        self.frame_name = name
        self.edge_data = edge_data

        fm = QFontMetrics(_FONT)
        text_w = fm.horizontalAdvance(name)
        text_h = fm.height()
        w = text_w + _NODE_PADDING_X * 2
        h = text_h + _NODE_PADDING_Y * 2

        self.setRect(0, 0, w, h)
        self.setPos(x - w / 2, y - h / 2)

        border = _CLR_ROOT_GLOW if is_root else (_CLR_NODE_STATIC_BORDER if is_static_only else _CLR_NODE_BORDER)
        self.setPen(QPen(border, 2))
        self.setBrush(QBrush(_CLR_NODE_FILL))

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

        # text child
        self._label = QGraphicsSimpleTextItem(name, self)
        self._label.setFont(_FONT)
        self._label.setBrush(QBrush(_CLR_NODE_TEXT))
        self._label.setPos(_NODE_PADDING_X, _NODE_PADDING_Y - 1)

        # tooltip
        tip = f"Frame: {name}"
        if edge_data:
            t = edge_data.translation
            r = edge_data.rotation
            tip += (
                f"\nParent: {edge_data.parent}"
                f"\nTranslation: ({t[0]:.3f}, {t[1]:.3f}, {t[2]:.3f})"
                f"\nRotation: ({r[0]:.3f}, {r[1]:.3f}, {r[2]:.3f}, {r[3]:.3f})"
                f"\nStatic: {edge_data.is_static}"
            )
        self.setToolTip(tip)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawRoundedRect(self.rect(), _NODE_RADIUS, _NODE_RADIUS)


class _EndpointDot(QGraphicsEllipseItem):
    """
    Filled circle marking the *start* of an edge.

    Uses ``ItemIgnoresTransformations`` so it stays a fixed pixel size
    regardless of zoom level.
    """

    _RADIUS = 5.0  # pixels on screen

    def __init__(self, cx: float, cy: float, colour: QColor, parent=None) -> None:
        r = self._RADIUS
        super().__init__(-r, -r, r * 2, r * 2, parent)
        self.setPos(cx, cy)
        self.setPen(Qt.PenStyle.NoPen)
        self.setBrush(QBrush(colour))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(10)  # always on top


class _EndpointTriangle(QGraphicsPathItem):
    """
    Filled downward-pointing triangle marking the *end* of an edge.

    Uses ``ItemIgnoresTransformations`` so it stays a fixed pixel size
    regardless of zoom level.
    """

    _SIZE = 12.0  # half-width / height in pixels

    def __init__(self, cx: float, cy: float, colour: QColor, parent=None) -> None:
        super().__init__(parent)
        self.setPos(cx, cy)

        sz = self._SIZE
        tri = QPainterPath()
        tri.moveTo(0, sz * 0.7)  # bottom tip
        tri.lineTo(-sz * 0.6, -sz * 0.4)  # top-left
        tri.lineTo(sz * 0.6, -sz * 0.4)  # top-right
        tri.closeSubpath()
        self.setPath(tri)

        self.setPen(Qt.PenStyle.NoPen)
        self.setBrush(QBrush(colour))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(10)  # always on top


class EdgeItem(QGraphicsPathItem):
    """
    Curved edge between two nodes.

    Visual markers that are *always* visible regardless of zoom:
    - **Start (parent)**: filled circle / dot
    - **End (child)**: filled triangle pointing toward the child
    """

    def __init__(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        is_static: bool,
        scene: QGraphicsScene,
    ) -> None:
        super().__init__()
        colour = _CLR_EDGE_STATIC if is_static else _CLR_EDGE_DYNAMIC
        pen = QPen(colour, _EDGE_WIDTH)
        if is_static:
            pen.setDashPattern([6, 3])
        self.setPen(pen)
        self.setBrush(Qt.BrushStyle.NoBrush)

        # Bézier curve
        path = QPainterPath()
        path.moveTo(x1, y1)
        mid_y = (y1 + y2) / 2
        path.cubicTo(x1, mid_y, x2, mid_y, x2, y2)
        self.setPath(path)

        # ── endpoint markers (added as independent scene items so
        #    ItemIgnoresTransformations works correctly) ──────────
        self._dot = _EndpointDot(x1, y1, colour)
        scene.addItem(self._dot)

        self._tri = _EndpointTriangle(x2, y2, colour)
        scene.addItem(self._tri)


# ── Main Viewer Widget ──────────────────────────────────────────────


class TFGraphView(QGraphicsView):
    """Pannable, zoomable view of the TF tree."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(_CLR_BG))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._zoom = 1.0

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoom *= factor
        self._zoom = max(0.1, min(self._zoom, 10.0))
        self.setTransform(self.transform().scale(factor, factor))


# ── Main Window ─────────────────────────────────────────────────────


class TFVisualizerWindow(QMainWindow):
    """
    Top-level window.

    A 60 Hz QTimer polls the TFGraph revision; when a change is detected
    the scene is rebuilt from the new layout.  This keeps the GUI
    responsive — no signals cross the ROS / Qt thread boundary.
    """

    def __init__(self, graph: TFGraph, on_force_refresh=None) -> None:
        super().__init__()
        self._graph = graph
        self._on_force_refresh = on_force_refresh
        self._last_rev: int = -1

        self.setWindowTitle("TF2 Graph Visualizer")
        self.resize(1280, 800)

        # Central widget
        self._scene = QGraphicsScene(self)
        self._view = TFGraphView(self)
        self._view.setScene(self._scene)
        self.setCentralWidget(self._view)

        # Status bar
        self._status = QStatusBar(self)
        self.setStatusBar(self._status)
        self._status_label = QLabel("Waiting for TF messages …")
        self._status_label.setFont(_FONT)
        self._status_label.setStyleSheet(f"color: {_CLR_STATUS_TEXT.name()};")
        self._status.addWidget(self._status_label)

        # Refresh Button
        self._refresh_btn = QPushButton("⟳")
        self._refresh_btn.setFont(_FONT_BOLD)
        self._refresh_btn.setStyleSheet(
            f"QPushButton {{ color: {_CLR_STATUS_TEXT.name()}; background: transparent; border: none; }}"
            f"QPushButton:hover {{ color: {_CLR_NODE_BORDER.name()}; }}"
        )
        self._refresh_btn.setToolTip("Force refresh")
        self._refresh_btn.clicked.connect(self._refresh)
        self._status.addPermanentWidget(self._refresh_btn)

        # Legend
        self._legend_label = QLabel()
        self._legend_label.setFont(_FONT)
        self._legend_label.setStyleSheet(f"color: {_CLR_STATUS_TEXT.name()};")
        self._legend_label.setText(
            f'<span style="color:{_CLR_EDGE_DYNAMIC.name()};">━━ dynamic</span>'
            f"&nbsp;&nbsp;"
            f'<span style="color:{_CLR_EDGE_STATIC.name()};">╌╌ static</span>'
            f"&nbsp;&nbsp;"
            f'<span style="color:{_CLR_ROOT_GLOW.name()};">■ root</span>'
            f"&nbsp;&nbsp;"
            f'<span style="color:{_CLR_STATUS_TEXT.name()};">● start &nbsp;▶ end</span>'
        )
        self._status.addPermanentWidget(self._legend_label)

        # Poll timer  (16 ms ≈ 60 fps check rate; actual repaint only on change)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(16)

        # Prune timer — remove stale dynamic edges every 2 s
        self._prune_timer = QTimer(self)
        self._prune_timer.timeout.connect(self._prune)
        self._prune_timer.start(2000)

        self._apply_stylesheet()

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            f"""
            QMainWindow {{
                background: {_CLR_BG.name()};
            }}
            QStatusBar {{
                background: {_CLR_NODE_FILL.name()};
                border-top: 1px solid {_CLR_NODE_BORDER.name()};
            }}
            QToolTip {{
                background: {_CLR_TOOLTIP_BG.name()};
                color: {_CLR_NODE_TEXT.name()};
                border: 1px solid {_CLR_NODE_BORDER.name()};
                padding: 4px;
                font-family: Monospace;
            }}
        """
        )

    # ── polling / repaint ───────────────────────────────────────

    def _refresh(self) -> None:
        """Clear graph, re-fetch TF data, and rebuild the scene."""
        if self._on_force_refresh:
            self._on_force_refresh()
        self._last_rev = -1
        self._poll()

    def _poll(self) -> None:
        rev = self._graph.revision
        if rev != self._last_rev:
            self._last_rev = rev
            self._rebuild_scene()

    def _prune(self) -> None:
        self._graph.prune_stale()

    def _rebuild_scene(self) -> None:
        rev, edges = self._graph.snapshot()
        layout = compute_layout(edges)

        self._scene.clear()

        if not layout.nodes:
            self._status_label.setText("Waiting for TF messages …")
            return

        roots = self._graph.roots()

        # Determine which nodes only have static edges
        static_only_nodes: set = set()
        has_dynamic: set = set()
        for e in edges.values():
            if e.is_static:
                static_only_nodes.add(e.child)
            else:
                has_dynamic.add(e.child)
        static_only_nodes -= has_dynamic

        # Collect edge data per child for tooltip
        child_edge_map: Dict[str, FrameEdge] = {}
        for e in edges.values():
            child_edge_map[e.child] = e

        # Draw edges first (underneath nodes)
        fm = QFontMetrics(_FONT)
        node_h = fm.height() + _NODE_PADDING_Y * 2

        for parent_name, child_name, is_static in layout.edges:
            if parent_name not in layout.nodes or child_name not in layout.nodes:
                continue
            px, py = layout.nodes[parent_name]
            cx, cy = layout.nodes[child_name]
            edge_item = EdgeItem(px, py + node_h / 2, cx, cy - node_h / 2, is_static, self._scene)
            self._scene.addItem(edge_item)

        # Draw nodes
        for name, (nx, ny) in layout.nodes.items():
            is_root = name in roots
            is_so = name in static_only_nodes
            node = NodeItem(
                name,
                nx,
                ny,
                is_root=is_root,
                is_static_only=is_so,
                edge_data=child_edge_map.get(name),
            )
            self._scene.addItem(node)

        self._status_label.setText(f"Frames: {len(layout.nodes)}  |  " f"Edges: {len(layout.edges)}  |  " f"Rev: {rev}")

        # Fit scene with some padding
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-80, -60, 80, 60))
