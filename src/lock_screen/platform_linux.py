"""Linux-specific backends: screenshot capture, display geometry, and screen locking."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

# -- Screenshot methods ----------------------------------------------------


def _run(cmd: list[str], output_path: str) -> bool:
    """Run a command and return True if it succeeded and produced a non-empty file."""
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return os.path.isfile(output_path) and os.path.getsize(output_path) > 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def try_cosmic_screenshot(path: str) -> bool:
    """cosmic-screenshot (COSMIC desktop)."""
    output_dir = os.path.dirname(path) or "."
    try:
        result = subprocess.run(
            ["cosmic-screenshot", "-s", output_dir, "--interactive=false"],
            check=True,
            capture_output=True,
            text=True,
        )
        actual_path = result.stdout.strip()
        if actual_path and os.path.isfile(actual_path) and os.path.getsize(actual_path) > 0:
            if actual_path != path:
                shutil.move(actual_path, path)
            return os.path.isfile(path) and os.path.getsize(path) > 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return False


def try_grim(path: str) -> bool:
    """grim (wlroots-compatible: sway, COSMIC, etc.)."""
    return _run(["grim", path], path)


def try_gnome_screenshot(path: str) -> bool:
    """gnome-screenshot (GNOME Wayland/X11)."""
    return _run(["gnome-screenshot", "-f", path], path)


def try_spectacle(path: str) -> bool:
    """spectacle (KDE Plasma)."""
    return _run(["spectacle", "-b", "-n", "-f", "-o", path], path)


def try_xdg_portal(path: str) -> bool:
    """XDG Desktop Portal (universal Wayland fallback)."""
    script = """\
import os, sys, shutil
from urllib.parse import urlparse, unquote
try:
    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    loop = GLib.MainLoop()
    result_uri = [None]
    def on_response(response, results):
        if response == 0 and 'uri' in results:
            result_uri[0] = str(results['uri'])
        loop.quit()
    portal = bus.get_object('org.freedesktop.portal.Desktop',
                            '/org/freedesktop/portal/desktop')
    iface = dbus.Interface(portal, 'org.freedesktop.portal.Screenshot')
    request_path = iface.Screenshot('', {'interactive': dbus.Boolean(False)})
    bus.add_signal_receiver(on_response,
        signal_name='Response',
        dbus_interface='org.freedesktop.portal.Request',
        path=request_path)
    GLib.timeout_add_seconds(5, loop.quit)
    loop.run()
    if result_uri[0]:
        src = unquote(urlparse(result_uri[0]).path)
        shutil.copy2(src, os.environ['SCREENSHOT_OUTPUT'])
        sys.exit(0)
except Exception:
    pass
sys.exit(1)
"""
    try:
        env = {**os.environ, "SCREENSHOT_OUTPUT": path}
        subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            env=env,
        )
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def try_scrot(path: str) -> bool:
    """scrot (X11 fallback)."""
    return _run(["scrot", path], path)


def try_import(path: str) -> bool:
    """ImageMagick import (X11 fallback)."""
    return _run(["import", "-window", "root", path], path)


SCREENSHOT_METHODS = [
    try_cosmic_screenshot,
    try_gnome_screenshot,
    try_spectacle,
    try_xdg_portal,
    try_scrot,
    try_import,
]


# -- Display geometry ------------------------------------------------------


def get_display_geometries() -> list[dict[str, int]]:
    """Detect connected displays via wlr-randr or xrandr."""
    displays: list[dict[str, int]] = []

    # Try wlr-randr first (wlroots compositors)
    try:
        result = subprocess.run(["wlr-randr"], capture_output=True, text=True, check=True)
        current_display: str | None = None
        geometry: dict[str, int] = {}

        for line in result.stdout.splitlines():
            stripped = line.strip()

            if not line.startswith(" ") and not line.startswith("\t") and stripped:
                if current_display and geometry.get("width"):
                    displays.append(geometry)
                current_display = stripped.split()[0]
                geometry = {"width": 0, "height": 0, "x": 0, "y": 0}

            if "current" in stripped and "x" in stripped:
                parts = stripped.replace("current", "").strip().split()
                if parts:
                    res = parts[0]
                    if "x" in res:
                        w, h = res.split("x")[:2]
                        try:
                            geometry["width"] = int(w)
                            geometry["height"] = int(h)
                        except ValueError:
                            pass

            if "Position" in stripped or "position" in stripped:
                parts = stripped.split()
                for part in parts:
                    if "," in part:
                        try:
                            x, y = part.split(",")
                            geometry["x"] = int(x)
                            geometry["y"] = int(y)
                        except ValueError:
                            pass

        if current_display and geometry.get("width"):
            displays.append(geometry)

        if displays:
            return displays
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fallback: xrandr
    try:
        result = subprocess.run(["xrandr", "--query"], capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if " connected" in line:
                match = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)", line)
                if match:
                    displays.append(
                        {
                            "width": int(match.group(1)),
                            "height": int(match.group(2)),
                            "x": int(match.group(3)),
                            "y": int(match.group(4)),
                        }
                    )
        if displays:
            return displays
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return displays


# -- Screen locking --------------------------------------------------------


def lock_wayland(image_path: str) -> None:
    """Lock using swaylock for Wayland sessions."""
    try:
        subprocess.run(["swaylock", "-f", "-i", image_path], check=True)
    except FileNotFoundError:
        print("Error: No Wayland-compatible lock utility found.", file=sys.stderr)
        print("  sudo apt install swaylock", file=sys.stderr)
        sys.exit(1)


def lock_x11(image_path: str) -> None:
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


def lock(image_path: str) -> None:
    """Lock the screen on Linux using the appropriate backend."""
    session_type = os.environ.get("XDG_SESSION_TYPE", "")
    if session_type == "wayland":
        lock_wayland(image_path)
    else:
        lock_x11(image_path)
