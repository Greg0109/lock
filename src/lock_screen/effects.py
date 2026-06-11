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


def process_output_fast(
    output_name: str,
    width: int,
    height: int,
    output_path: str,
    pixelate_scale: int,
    blur_radius: float,
    blur_sigma: float,
    icon_path: str | None,
) -> None:
    """Capture one Wayland output via grim and apply all effects in a single pipeline.

    grim emits uncompressed PPM on stdout; ImageMagick reads it and writes the final PNG
    in one pass — no intermediate decode/encode of the full-size image.
    """
    grim = subprocess.Popen(
        ["grim", "-t", "ppm", "-o", output_name, "-"],
        stdout=subprocess.PIPE,
    )
    convert_cmd: list[str] = [
        "convert",
        "ppm:-",
        "-scale",
        f"{pixelate_scale}%",
        "-scale",
        "1000%",
        "-blur",
        f"{blur_radius},{blur_sigma}",
        "-resize",
        f"{width}x{height}!",
    ]
    if icon_path:
        convert_cmd += [icon_path, "-gravity", "center", "-composite"]
    convert_cmd += ["-define", "png:compression-level=1", output_path]

    try:
        result = subprocess.run(
            convert_cmd,
            stdin=grim.stdout,
            check=False,
            capture_output=True,
        )
    finally:
        if grim.stdout:
            grim.stdout.close()
        grim.wait()

    if grim.returncode != 0:
        raise subprocess.CalledProcessError(grim.returncode, grim.args)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, convert_cmd, output=result.stdout, stderr=result.stderr
        )


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
