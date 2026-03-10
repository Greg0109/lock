"""Screenshot capture — dispatches to platform-specific methods."""

from __future__ import annotations

import os
import platform
import sys
from typing import Callable

_IS_MACOS = platform.system() == "Darwin"


def _get_methods() -> list[Callable[[str], bool]]:
    if _IS_MACOS:
        from lock_screen.platform_macos import SCREENSHOT_METHODS
    else:
        from lock_screen.platform_linux import SCREENSHOT_METHODS
    return SCREENSHOT_METHODS


def capture(path: str) -> bool:
    """Try each screenshot method in order, return True on first success."""
    print(f"Attempting to capture screenshot to {path} using multiple methods...", file=sys.stderr)
    for method in _get_methods():
        try:
            method(path)
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                print(f"  {method.__name__} succeeded.", file=sys.stderr)
                return True
            else:
                print(
                    f"  {method.__name__} ran but did not produce a valid screenshot.",
                    file=sys.stderr,
                )
        except Exception as e:
            print(f"Warning: {method.__name__} failed with error: {e}", file=sys.stderr)
            continue
    return False
