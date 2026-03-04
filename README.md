# TF2 Graph Visualizer

Real-time ROS 2 TF tree viewer with a Qt GUI. Subscribes to `/tf` and `/tf_static`, builds the frame tree, and renders an interactive graph that updates live as transforms arrive.

![architecture](https://img.shields.io/badge/Python-3.10+-blue) ![ROS2](https://img.shields.io/badge/ROS2-Humble%2FIron%2FJazzy-green)

## Features

- **Live updates** — graph repaints automatically when new frames appear or stale ones expire
- **Pan & zoom** — scroll-wheel zoom, click-drag pan via `QGraphicsView`
- **Colour-coded edges** — solid blue for dynamic transforms, dashed green for static
- **Root highlighting** — root frames shown with a purple border
- **Tooltips** — hover any node to see parent, translation, rotation, and static flag
- **Stale pruning** — dynamic edges not seen for 10 s are automatically removed
- **Thread-safe** — ROS callbacks run on a daemon thread; Qt main loop is never blocked

## Architecture

```
┌──────────────────┐        ┌──────────────┐
│  ROS 2 spin      │──edge──▶   TFGraph    │
│  (daemon thread) │ updates│ (thread-safe) │
└──────────────────┘        └──────┬───────┘
                                   │ revision poll (60 Hz)
                            ┌──────▼───────┐
                            │  Qt GUI      │
                            │  (main loop) │
                            └──────────────┘
```

The ROS subscriber thread writes edges into `TFGraph`. A monotonic revision counter is bumped on structural changes. The Qt timer polls this counter at ~60 fps and only rebuilds the scene when the revision has changed.

## Prerequisites

```bash
# ROS 2 (Humble / Iron / Jazzy) must be sourced
source /opt/ros/${ROS_DISTRO}/setup.bash

# Python deps
pip install PySide6
```

## Installation

```bash
# Option A: install as a package
pip install .

# Option B: run directly
python -m tf2_visualizer
```

## Usage

```bash
# Terminal 1 — make sure ROS 2 is sourced
source /opt/ros/humble/setup.bash

# Terminal 2 — run the visualizer
tf2-visualizer          # if installed via pip
# or
python -m tf2_visualizer

# Terminal 3 — publish some test transforms
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

## File Structure

```
tf2_visualizer/
├── __init__.py
├── __main__.py        # python -m entry point
├── main.py            # application bootstrap
├── graph.py           # thread-safe TF tree data model
├── layout.py          # Reingold-Tilford tree layout engine
├── ros_listener.py    # ROS 2 /tf + /tf_static subscriber
└── gui.py             # PySide6 Qt graphics view + window
```
