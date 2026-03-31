from setuptools import find_packages, setup

package_name = "tf2_visualizer_pkg"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools", "PySide6"],
    zip_safe=True,
    maintainer="jan",
    maintainer_email="email@example.com",
    description="A ROS 2 package that visualizes the TF2 graph using a Qt GUI.",
    license="Apache-2.0",
    extras_require={
        "test": [
            "pytest",
        ],
    },
    entry_points={
        "console_scripts": [
            "tf2_visualizer = tf2_visualizer_pkg.main:main",
        ],
    },
)
