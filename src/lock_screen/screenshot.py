"""Screenshot capture methods for various display servers and compositors."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def _run(cmd: list[str], output_path: str) -> bool:
    """Run a command and return True if it succeeded and produced a non-empty file."""
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return os.path.isfile(output_path) and os.path.getsize(output_path) > 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _try_cosmic_screenshot(path: str) -> bool:
    """Method 1: cosmic-screenshot (COSMIC desktop).

    cosmic-screenshot does not allow choosing the output filename.
    It saves as Screenshot_<datetime>.png in the directory given by -s
    and prints the resulting path to stdout.
    """
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


def _try_grim(path: str) -> bool:
    """Method 2: grim (wlroots-compatible: sway, COSMIC, etc.)."""
    return _run(["grim", path], path)


def _try_gnome_screenshot(path: str) -> bool:
    """Method 3: gnome-screenshot (GNOME Wayland/X11)."""
    return _run(["gnome-screenshot", "-f", path], path)


def _try_spectacle(path: str) -> bool:
    """Method 4: spectacle (KDE Plasma)."""
    return _run(["spectacle", "-b", "-n", "-f", "-o", path], path)


def _try_xdg_portal(path: str) -> bool:
    """Method 5: XDG Desktop Portal (universal Wayland fallback)."""
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


def _try_scrot(path: str) -> bool:
    """Method 6: scrot (X11 fallback)."""
    return _run(["scrot", path], path)


def _try_import(path: str) -> bool:
    """Method 7: ImageMagick import (X11 fallback)."""
    return _run(["import", "-window", "root", path], path)


METHODS = [
    _try_cosmic_screenshot,
    _try_gnome_screenshot,
    _try_spectacle,
    _try_xdg_portal,
    _try_scrot,
    _try_import,
]


def capture(path: str) -> bool:
    """Try each screenshot method in order, return True on first success."""
    print(f"Attempting to capture screenshot to {path} using multiple methods...", file=sys.stderr)
    for method in METHODS:
        try:
            method(path)
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                print(f"  {method.__name__} succeeded.", file=sys.stderr)
                return True
            else:
                print(f"  {method.__name__} ran but did not produce a valid screenshot.", file=sys.stderr)
        except Exception as e:
            print(f"Warning: {method.__name__} failed with error: {e}", file=sys.stderr)
            continue
    return False
