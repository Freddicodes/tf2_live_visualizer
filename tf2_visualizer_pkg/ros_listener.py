"""
tf2_visualizer_pkg.ros_listener — ROS 2 subscriber for /tf and /tf_static.

Runs the rclpy spin loop on a daemon thread so the GUI main loop is
never blocked.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from geometry_msgs.msg import TransformStamped
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from tf2_msgs.msg import TFMessage

if TYPE_CHECKING:
    from tf2_visualizer_pkg.graph import TFGraph


# /tf_static uses transient-local durability so late-joining subscribers
# still receive the last published message.
_QOS_TF = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=100,
)

_QOS_TF_STATIC = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=100,
)


class TFListenerNode(Node):
    """Lightweight ROS 2 node that populates a :class:`TFGraph`."""

    def __init__(self, graph: TFGraph) -> None:
        super().__init__("tf2_graph_visualizer")
        self._graph = graph

        self.create_subscription(TFMessage, "/tf", self._on_tf, _QOS_TF)
        self._static_sub = self.create_subscription(TFMessage, "/tf_static", self._on_tf_static, _QOS_TF_STATIC)
        self.get_logger().info("Subscribed to /tf and /tf_static")

    # ── callbacks ───────────────────────────────────────────────────

    def force_refresh(self) -> None:
        """Clear the graph and re-subscribe to /tf_static to replay static transforms."""
        self._graph.clear()
        self.destroy_subscription(self._static_sub)
        self._static_sub = self.create_subscription(
            TFMessage, "/tf_static", self._on_tf_static, _QOS_TF_STATIC
        )

    def _on_tf(self, msg: TFMessage) -> None:
        self._ingest(msg, is_static=False)

    def _on_tf_static(self, msg: TFMessage) -> None:
        self._ingest(msg, is_static=True)

    def _ingest(self, msg: TFMessage, *, is_static: bool) -> None:
        tf: TransformStamped
        for tf in msg.transforms:
            t = tf.transform.translation
            r = tf.transform.rotation
            self._graph.update_edge(
                parent=tf.header.frame_id,
                child=tf.child_frame_id,
                is_static=is_static,
                translation=(t.x, t.y, t.z),
                rotation=(r.x, r.y, r.z, r.w),
            )


class ROSSpinThread(threading.Thread):
    """Daemon thread that drives the rclpy executor."""

    def __init__(self, node: TFListenerNode) -> None:
        super().__init__(daemon=True, name="ros-spin")
        self._node = node
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(node)

    def run(self) -> None:
        try:
            self._executor.spin()
        except ExternalShutdownException:
            pass
        finally:
            self._executor.shutdown()

    def shutdown(self) -> None:
        self._executor.shutdown()
        self._node.destroy_node()
