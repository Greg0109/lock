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


def _is_macos_session_locked() -> bool:
    """Check whether the macOS session is currently locked."""
    import ctypes
    import ctypes.util

    cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

    cg.CGSessionCopyCurrentDictionary.restype = ctypes.c_void_p
    cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    cf.CFBooleanGetValue.restype = ctypes.c_bool
    cf.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
    cf.CFRelease.argtypes = [ctypes.c_void_p]

    # Create CFString for the key
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    k_utf8 = 0x08000100
    key = cf.CFStringCreateWithCString(None, b"CGSSessionScreenIsLocked", k_utf8)

    try:
        d = cg.CGSessionCopyCurrentDictionary()
        if not d:
            return False
        try:
            val = cf.CFDictionaryGetValue(d, key)
            if not val:
                return False
            return cf.CFBooleanGetValue(val)
        finally:
            cf.CFRelease(d)
    finally:
        if key:
            cf.CFRelease(key)


def _wait_for_macos_unlock() -> None:
    """Block until the session locks and then unlocks."""
    # Phase 1: wait for the session to actually lock
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if _is_macos_session_locked():
            print("  Session is locked.", file=sys.stderr)
            break
        time.sleep(0.3)
    else:
        print("  Session never locked, restoring immediately.", file=sys.stderr)
        return

    # Phase 2: wait for the user to unlock
    while _is_macos_session_locked():
        time.sleep(1)

    print("  Session unlocked, restoring wallpaper.", file=sys.stderr)
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

        _wait_for_macos_unlock()
    finally:
        print("Restoring original wallpapers...", file=sys.stderr)
        _restore_macos_wallpapers(originals)
