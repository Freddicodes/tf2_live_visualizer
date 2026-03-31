# TF2 Graph Visualizer

Real-time ROS 2 TF tree viewer with a Qt GUI. Subscribes to `/tf` and `/tf_static`, builds the frame tree, and renders an interactive graph that updates live as transforms arrive.

![architecture](https://img.shields.io/badge/Python-3.12+-blue) ![ROS2](https://img.shields.io/badge/ROS2-Jazzy-green)

## Features

- **Live updates** — graph repaints automatically when new frames appear or stale ones expire
- **Pan & zoom** — scroll-wheel zoom, click-drag pan via `QGraphicsView`
- **Color-coded edges** — solid blue for dynamic transforms, dashed green for static
- **Root highlighting** — root frames shown with a purple border
- **Tooltips** — hover any node to see parent, translation, rotation, and static flag
- **Stale pruning** — dynamic edges not seen for 10 s are automatically removed
- **Thread-safe** — ROS callbacks run on a daemon thread; Qt main loop is never blocked
- **Manual refresh** — click the ⟳ button to force an immediate scene rebuild

## Architecture

```
┌──────────────────┐         ┌──────────────┐
│  ROS 2 spin      │──edge──▶|    FGraph    │
│  (daemon thread) │ updates │ (thread-safe)│
└──────────────────┘         └──────┬───────┘
                                    │ revision poll (60 Hz)
                             ┌──────▼───────┐
                             │  Qt GUI      │
                             │  (main loop) │
                             └──────────────┘
```

The ROS subscriber thread writes edges into `TFGraph`.

## Prerequisites

```bash
# ROS 2 (Humble / Iron / Jazzy) must be sourced
source /opt/ros/${ROS_DISTRO}/setup.${SHELL##*/}

# Python deps
pip install PySide6
```

## Usage

```bash
# Terminal 1 — run the visualizer
colcon build --packages-select tf2_visualizer_pkg
source install/setup.${SHELL##*/}
ros2 run tf2_visualizer_pkg tf2_visualizer

# Terminal 2 — publish some test transforms 
ros2 run tf2_ros static_transform_publisher 0 0 1 0 0 0 world base_link
ros2 run tf2_ros static_transform_publisher 0 0.5 0 0 0 0 base_link camera_link
ros2 run tf2_ros static_transform_publisher 0 0 0.3 0 0 0 base_link lidar_link
```

## Controls

| Action | Input |
|---|---|
| Pan | Click + drag |
| Zoom | Scroll wheel |
| Inspect frame | Hover node |
| Select node | Click |

## Configuration

Edit `TFGraph(stale_timeout=...)` in `main.py` to change how long dynamic edges persist after their last update (default 10 s).

## AI use 

This application was coded with AI as it is not intended for serious use. It is intended for debugging / visualization.
