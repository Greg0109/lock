"""Screen locking — dispatches to platform-specific backends."""

from __future__ import annotations

import platform


def lock(image_path: str) -> None:
    """Lock the screen using the appropriate backend."""
    if platform.system() == "Darwin":
        from lock_screen.platform_macos import lock as _lock
    else:
        from lock_screen.platform_linux import lock as _lock
    _lock(image_path)
