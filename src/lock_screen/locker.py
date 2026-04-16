"""Screen locking backends for Wayland and X11."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile


def lock(image_path: str) -> None:
    """Lock the screen using the appropriate backend."""
    session_type = os.environ.get("XDG_SESSION_TYPE", "")

    if session_type == "wayland":
        _lock_wayland(image_path)
    else:
        _lock_x11(image_path)


def _get_wayland_outputs() -> list[dict[str, int | str]]:
    """Get output names and geometry for Wayland compositors.

    Returns entries with keys: name, width, height, x, y.
    """
    outputs: list[dict[str, int | str]] = []

    # Hyprland: structured monitor info with names and geometry.
    try:
        result = subprocess.run(
            ["hyprctl", "monitors", "-j"],
            capture_output=True,
            text=True,
            check=True,
        )
        monitors = json.loads(result.stdout)
        if isinstance(monitors, list):
            for monitor in monitors:
                if not isinstance(monitor, dict):
                    continue
                name = str(monitor.get("name", "")).strip()
                width = int(monitor.get("width", 0))
                height = int(monitor.get("height", 0))
                x = int(monitor.get("x", 0))
                y = int(monitor.get("y", 0))
                if name and width > 0 and height > 0:
                    outputs.append(
                        {
                            "name": name,
                            "width": width,
                            "height": height,
                            "x": x,
                            "y": y,
                        }
                    )
        if outputs:
            return outputs
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError, ValueError):
        pass

    # wlroots compositors: parse wlr-randr output.
    try:
        result = subprocess.run(["wlr-randr"], capture_output=True, text=True, check=True)
        current_name: str | None = None
        geometry: dict[str, int | str] = {}

        for line in result.stdout.splitlines():
            stripped = line.strip()

            if not line.startswith((" ", "\t")) and stripped:
                if current_name and int(geometry.get("width", 0)) > 0:
                    outputs.append(geometry)
                current_name = stripped.split()[0]
                geometry = {"name": current_name, "width": 0, "height": 0, "x": 0, "y": 0}

            if "current" in stripped and "x" in stripped:
                parts = stripped.replace("current", "").strip().split()
                if parts and "x" in parts[0]:
                    width_str, height_str = parts[0].split("x")[:2]
                    try:
                        geometry["width"] = int(width_str)
                        geometry["height"] = int(height_str)
                    except ValueError:
                        pass

            if "Position" in stripped or "position" in stripped:
                for part in stripped.split():
                    if "," in part:
                        try:
                            x_str, y_str = part.split(",")
                            geometry["x"] = int(x_str)
                            geometry["y"] = int(y_str)
                        except ValueError:
                            pass

        if current_name and int(geometry.get("width", 0)) > 0:
            outputs.append(geometry)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return outputs


def _build_per_output_image_args(image_path: str, temp_dir: str) -> list[str]:
    """Build swaylock `-i output:path` arguments from a combined screenshot."""
    outputs = _get_wayland_outputs()
    if not outputs:
        return []

    min_x = min(int(output["x"]) for output in outputs)
    min_y = min(int(output["y"]) for output in outputs)
    image_args: list[str] = []

    try:
        for output in outputs:
            name = str(output["name"])
            width = int(output["width"])
            height = int(output["height"])
            crop_x = int(output["x"]) - min_x
            crop_y = int(output["y"]) - min_y
            cropped_path = os.path.join(temp_dir, f"{name}.png")

            subprocess.run(
                [
                    "convert",
                    image_path,
                    "-crop",
                    f"{width}x{height}+{crop_x}+{crop_y}",
                    "+repage",
                    cropped_path,
                ],
                check=True,
                capture_output=True,
            )

            if not os.path.isfile(cropped_path) or os.path.getsize(cropped_path) == 0:
                return []

            image_args.extend(["-i", f"{name}:{cropped_path}"])
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return []

    return image_args


def _lock_wayland(image_path: str) -> None:
    """Lock using swaylock for Wayland sessions."""
    try:
        with tempfile.TemporaryDirectory(prefix="lock-screen-") as temp_dir:
            image_args = _build_per_output_image_args(image_path, temp_dir)
            cmd = ["swaylock", "-f", *(image_args or ["-i", image_path])]
            subprocess.run(cmd, check=True)
    except FileNotFoundError:
        print("Error: No Wayland-compatible lock utility found.", file=sys.stderr)
        print("  sudo apt install swaylock", file=sys.stderr)
        sys.exit(1)


def _lock_x11(image_path: str) -> None:
    """Lock using i3lock-color or i3lock for X11 sessions."""
    for cmd in [["i3lock-color", "-n", "-i", image_path], ["i3lock", "-n", "-i", image_path]]:
        try:
            subprocess.run(cmd, check=True)
            return
        except FileNotFoundError:
            continue

    print("Error: No screen lock utility found.", file=sys.stderr)
    print("  sudo apt install i3lock-color", file=sys.stderr)
    sys.exit(1)
