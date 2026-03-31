#!/usr/bin/env python3
"""
tf2_visualizer_pkg — Real-time ROS 2 TF tree graph viewer.

Subscribes to /tf and /tf_static, builds a live directed tree of frames,
and renders it in a Qt window with pan, zoom, tooltips, and automatic
layout updates.

Architecture
------------
    ┌──────────────────┐          ┌──────────────┐
    │  ROS 2 spin      │──edge──▶ │ TFGraph      │
    │  (daemon thread) │  updates │ (thread-safe)│
    └──────────────────┘          └──────┬───────┘
                                         │ revision poll
                                  ┌──────▼───────┐
                                  │  Qt GUI      │
                                  │ (main thread)│
                                  └──────────────┘

The ROS callback thread writes into TFGraph; the Qt main thread polls
the graph revision counter every 16 ms and repaints only when the
topology has changed.
"""

import signal
import sys

import rclpy
from PySide6.QtWidgets import QApplication

from tf2_visualizer_pkg.graph import TFGraph
from tf2_visualizer_pkg.gui import TFVisualizerWindow
from tf2_visualizer_pkg.ros_listener import ROSSpinThread, TFListenerNode


def main() -> None:
    # ── ROS 2 init ──────────────────────────────────────────────
    rclpy.init(args=sys.argv)

    graph = TFGraph(stale_timeout=10.0)
    node = TFListenerNode(graph)
    ros_thread = ROSSpinThread(node)
    ros_thread.start()

    # ── Qt application ──────────────────────────────────────────
    app = QApplication(sys.argv)
    app.setApplicationName("TF2 Graph Visualizer")

    window = TFVisualizerWindow(graph, on_force_refresh=node.force_refresh)
    window.show()

    # Allow Ctrl-C to close gracefully
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    exit_code = app.exec()

    # ── Cleanup ─────────────────────────────────────────────────
    ros_thread.shutdown()
    rclpy.try_shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
