"""Screen locking backends for Wayland and X11."""

from __future__ import annotations

import os
import subprocess
import sys


def lock(image_path: str) -> None:
    """Lock the screen using the appropriate backend."""
    session_type = os.environ.get("XDG_SESSION_TYPE", "")

    if session_type == "wayland":
        _lock_wayland(image_path)
    else:
        _lock_x11(image_path)


def _lock_wayland(image_path: str) -> None:
    """Lock using swaylock for Wayland sessions."""
    try:
        subprocess.run(["swaylock", "-f", "-i", image_path], check=True)
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
