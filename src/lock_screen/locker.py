"""Screen locking backends for Wayland, X11, and macOS."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time


def lock(image_path: str) -> None:
    """Lock the screen using the appropriate backend."""
    if platform.system() == "Darwin":
        _lock_macos(image_path)
        return

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


# -- macOS support --------------------------------------------------------


def _get_macos_wallpapers() -> list[str]:
    """Return the current wallpaper POSIX path for each screen."""
    script = (
        "ObjC.import('AppKit');"
        "var screens = $.NSScreen.screens;"
        "var ws = $.NSWorkspace.sharedWorkspace;"
        "var paths = [];"
        "for (var i = 0; i < screens.count; i++) {"
        "  var url = ws.desktopImageURLForScreen(screens.objectAtIndex(i));"
        "  if (url) paths.push(url.path.js);"
        "}"
        "paths.join('\\n');"
    )
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]


def _set_macos_wallpaper(image_path: str) -> None:
    """Set all screens to the given wallpaper image."""
    script = (
        "ObjC.import('AppKit');"
        "var ws = $.NSWorkspace.sharedWorkspace;"
        "var screens = $.NSScreen.screens;"
        f"var url = $.NSURL.fileURLWithPath('{image_path}');"
        "for (var i = 0; i < screens.count; i++) {"
        "  ws.setDesktopImageURLForScreenOptionsError("
        "    url, screens.objectAtIndex(i), $(), $());"
        "}"
    )
    subprocess.run(["osascript", "-l", "JavaScript", "-e", script], check=True)


def _restore_macos_wallpapers(paths: list[str]) -> None:
    """Restore each screen to its original wallpaper."""
    if not paths:
        return
    set_lines = []
    for i, p in enumerate(paths):
        set_lines.append(
            f"  var url{i} = $.NSURL.fileURLWithPath('{p}');"
            f"  if ({i} < screens.count)"
            f"    ws.setDesktopImageURLForScreenOptionsError("
            f"      url{i}, screens.objectAtIndex({i}), $(), $());"
        )
    inner = "\n".join(set_lines)
    script = (
        "ObjC.import('AppKit');\n"
        "var ws = $.NSWorkspace.sharedWorkspace;\n"
        "var screens = $.NSScreen.screens;\n"
        f"{inner}"
    )
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Warning: wallpaper restore failed: {result.stderr.strip()}", file=sys.stderr)


def _is_macos_display_asleep() -> bool:
    """Check whether the macOS main display is currently asleep."""
    import ctypes

    cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cg.CGMainDisplayID.restype = ctypes.c_uint32
    cg.CGDisplayIsAsleep.restype = ctypes.c_int32
    cg.CGDisplayIsAsleep.argtypes = [ctypes.c_uint32]
    return bool(cg.CGDisplayIsAsleep(cg.CGMainDisplayID()))


def _wait_for_macos_unlock() -> None:
    """Block until the display sleeps and then wakes back up."""
    # Phase 1: wait for the display to actually go to sleep
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if _is_macos_display_asleep():
            print("  Display is asleep.", file=sys.stderr)
            break
        time.sleep(0.3)
    else:
        # Display never slept (user moved mouse in time) — nothing to wait for
        print("  Display never slept, restoring immediately.", file=sys.stderr)
        return

    # Phase 2: wait for the display to come back on (user unlocked)
    while _is_macos_display_asleep():
        time.sleep(1)

    print("  Display woke up, restoring wallpaper.", file=sys.stderr)
    # Small grace period so the desktop is fully rendered before wallpaper swap
    time.sleep(1)


def _lock_macos(image_path: str) -> None:
    """Lock macOS: swap wallpaper, sleep display, restore after unlock."""
    abs_path = os.path.abspath(image_path)
    originals = _get_macos_wallpapers()

    print(f"Original wallpapers: {originals}", file=sys.stderr)

    try:
        _set_macos_wallpaper(abs_path)
        time.sleep(0.5)

        try:
            subprocess.run(["pmset", "displaysleepnow"], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Error: Failed to lock screen via pmset.", file=sys.stderr)
            sys.exit(1)

        time.sleep(1)
        _wait_for_macos_unlock()
    finally:
        print("Restoring original wallpapers...", file=sys.stderr)
        _restore_macos_wallpapers(originals)
