"""Image effects: pixelation, blur, and lock icon compositing."""

from __future__ import annotations

import platform
import shutil
import subprocess

_MAGICK_CMD: list[str] | None = None


def _magick_cmd() -> list[str]:
    """Return the ImageMagick convert command, preferring IMv7 'magick'."""
    global _MAGICK_CMD  # noqa: PLW0603
    if _MAGICK_CMD is None:
        _MAGICK_CMD = ["magick"] if shutil.which("magick") else ["convert"]
    return _MAGICK_CMD


def _convert(args: list[str]) -> None:
    """Run an ImageMagick convert/magick command."""
    subprocess.run([*_magick_cmd(), *args], check=True)


def pixelate(image_path: str, scale_down: int = 10) -> None:
    """Pixelate an image by scaling down then back up."""
    _convert(
        [
            image_path,
            "-scale",
            f"{scale_down}%",
            "-scale",
            "1000%",
            image_path,
        ]
    )


def blur(image_path: str, radius: float = 2, sigma: float = 5) -> None:
    """Apply Gaussian blur to an image."""
    _convert([image_path, "-blur", f"{radius},{sigma}", image_path])


def _get_display_geometries() -> list[dict[str, int]]:
    """Detect connected displays — dispatches to platform-specific backend."""
    if platform.system() == "Darwin":
        from lock_screen.platform_macos import get_display_geometries
    else:
        from lock_screen.platform_linux import get_display_geometries
    return get_display_geometries()


def composite_icon(image_path: str, icon_path: str) -> None:
    """Overlay the lock icon centered on each detected display."""
    displays = _get_display_geometries()

    if not displays:
        _convert([image_path, icon_path, "-gravity", "center", "-composite", image_path])
        return

    identify_cmd = ["magick", "identify"] if shutil.which("magick") else ["identify"]
    result = subprocess.run(
        [*identify_cmd, "-format", "%w %h", icon_path],
        capture_output=True,
        text=True,
        check=True,
    )
    icon_w, icon_h = (int(v) for v in result.stdout.strip().split())

    for display in displays:
        center_x = display["x"] + (display["width"] - icon_w) // 2
        center_y = display["y"] + (display["height"] - icon_h) // 2
        _convert(
            [
                image_path,
                icon_path,
                "-geometry",
                f"+{center_x}+{center_y}",
                "-gravity",
                "NorthWest",
                "-composite",
                image_path,
            ]
        )
