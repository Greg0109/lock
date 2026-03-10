"""macOS-specific backends: screenshot, display geometry, wallpaper, and screen locking."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time


def delete_temp_file(path: str) -> None:
    """Delete the temporary screenshot file if it exists."""
    try:
        if os.path.isfile(path):
            os.remove(path)
    except Exception as e:
        print(f"Warning: Failed to delete temp file {path}: {e}", file=sys.stderr)

# -- Screenshot methods ----------------------------------------------------


def try_screencapture(path: str) -> bool:
    """screencapture (macOS built-in)."""
    try:
        subprocess.run(["screencapture", "-x", path], check=True, capture_output=True)
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


SCREENSHOT_METHODS = [
    try_screencapture,
]


# -- Display geometry ------------------------------------------------------


def get_display_geometries() -> list[dict[str, int]]:
    """Detect connected displays via system_profiler (native pixel resolution)."""
    displays: list[dict[str, int]] = []
    try:
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        for controller in data.get("SPDisplaysDataType", []):
            for display in controller.get("spdisplays_ndrvs", []):
                # Prefer native pixel resolution (matches screencapture output)
                pixel_res = display.get("_spdisplays_pixels", "")
                if pixel_res and "x" in pixel_res:
                    parts = pixel_res.strip().split(" x ")
                else:
                    res = display.get("_spdisplays_resolution", "")
                    if "x" not in res:
                        continue
                    parts = res.split("@")[0].strip().split(" x ")
                if len(parts) == 2:
                    try:
                        w = int(parts[0].strip())
                        h = int(parts[1].strip())
                        displays.append({"width": w, "height": h, "x": 0, "y": 0})
                    except ValueError:
                        pass
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        pass
    return displays


# -- Wallpaper management --------------------------------------------------


def get_wallpapers() -> list[str]:
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


def set_wallpaper(image_path: str) -> None:
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


def restore_wallpapers(paths: list[str]) -> None:
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


# -- Session lock detection ------------------------------------------------

_cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
_cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

_cg.CGSessionCopyCurrentDictionary.restype = ctypes.c_void_p
_cf.CFDictionaryGetValue.restype = ctypes.c_void_p
_cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_cf.CFBooleanGetValue.restype = ctypes.c_bool
_cf.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
_cf.CFRelease.argtypes = [ctypes.c_void_p]
_cf.CFStringCreateWithCString.restype = ctypes.c_void_p
_cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]

_K_UTF8 = 0x08000100
_LOCK_KEY = _cf.CFStringCreateWithCString(None, b"CGSSessionScreenIsLocked", _K_UTF8)


def is_session_locked() -> bool:
    """Check whether the macOS session is currently locked."""
    d = _cg.CGSessionCopyCurrentDictionary()
    if not d:
        return False
    try:
        val = _cf.CFDictionaryGetValue(d, _LOCK_KEY)
        if not val:
            return False
        return _cf.CFBooleanGetValue(val)
    finally:
        _cf.CFRelease(d)


# -- Screen locking --------------------------------------------------------


def _wait_for_unlock() -> None:
    """Block until the session locks and then unlocks."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if is_session_locked():
            print("  Session is locked.", file=sys.stderr)
            break
        time.sleep(0.3)
    else:
        print("  Session never locked, restoring immediately.", file=sys.stderr)
        return

    while is_session_locked():
        time.sleep(1)

    print("  Session unlocked, restoring wallpaper.", file=sys.stderr)
    time.sleep(1)


def lock(image_path: str) -> None:
    """Lock macOS: swap wallpaper, sleep display, restore after unlock."""
    abs_path = os.path.abspath(image_path)
    originals = get_wallpapers()

    print(f"Original wallpapers: {originals}", file=sys.stderr)

    try:
        set_wallpaper(abs_path)
        time.sleep(0.5)

        try:
            subprocess.run(["pmset", "displaysleepnow"], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Error: Failed to lock screen via pmset.", file=sys.stderr)
            sys.exit(1)

        _wait_for_unlock()
    finally:
        print("Restoring original wallpapers...", file=sys.stderr)
        restore_wallpapers(originals)
        delete_temp_file(abs_path)
