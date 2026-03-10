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
    """Return the current wallpaper POSIX path for each desktop."""
    script = (
        'tell application "System Events"\n'
        "  set desktopCount to count of desktops\n"
        '  set paths to ""\n'
        "  repeat with i from 1 to desktopCount\n"
        "    set paths to paths & POSIX path of picture of desktop i & linefeed\n"
        "  end repeat\n"
        "  return paths\n"
        "end tell"
    )
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]


def _set_macos_wallpaper(image_path: str) -> None:
    """Set all desktops to the given wallpaper image."""
    safe = image_path.replace('"', '\\"')
    script = (
        f'tell application "System Events" to set picture of every desktop to POSIX file "{safe}"'
    )
    subprocess.run(["osascript", "-e", script], check=True)


def _restore_macos_wallpapers(paths: list[str]) -> None:
    """Restore each desktop to its original wallpaper."""
    if not paths:
        return
    lines = []
    for i, p in enumerate(paths, 1):
        safe = p.replace('"', '\\"')
        lines.append(f'  set picture of desktop {i} to POSIX file "{safe}"')
    inner = "\n".join(lines)
    script = f'tell application "System Events"\n{inner}\nend tell'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def _is_macos_screen_locked() -> bool:
    """Check whether the macOS session is currently locked."""
    script = (
        "ObjC.import('Quartz');"
        "var d = $.CGSessionCopyCurrentDictionary();"
        "var v = d.objectForKey('CGSSessionScreenIsLocked');"
        "v ? v.boolValue : false;"
    )
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() == "true"
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return False


def _wait_for_macos_unlock() -> None:
    """Block until the user unlocks the screen after a lock event."""
    was_locked = False
    unlocked_checks = 0
    while True:
        if _is_macos_screen_locked():
            was_locked = True
            unlocked_checks = 0
        elif was_locked:
            # Transitioned from locked → unlocked
            return
        else:
            unlocked_checks += 1
            if unlocked_checks > 15:
                # ~30 s without ever locking — display woke within grace period
                return
        time.sleep(2)


def _lock_macos(image_path: str) -> None:
    """Lock macOS: swap wallpaper, sleep display, restore after unlock."""
    abs_path = os.path.abspath(image_path)
    originals = _get_macos_wallpapers()

    try:
        _set_macos_wallpaper(abs_path)
        time.sleep(0.5)

        try:
            subprocess.run(["pmset", "displaysleepnow"], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Error: Failed to lock screen via pmset.", file=sys.stderr)
            sys.exit(1)

        time.sleep(3)
        _wait_for_macos_unlock()
    finally:
        _restore_macos_wallpapers(originals)
