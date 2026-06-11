"""Image effects: pixelation, blur, and lock icon compositing."""

from __future__ import annotations

import shutil
import subprocess

# ImageMagick 7 deprecates `convert`; prefer `magick` when available.
IM_BINARY = shutil.which("magick") or "convert"


def _convert(args: list[str]) -> None:
    """Run an ImageMagick command."""
    subprocess.run([IM_BINARY, *args], check=True)


def process_output_fast(
    output_name: str,
    width: int,
    height: int,
    output_path: str,
    pixelate_scale: int,
    blur_radius: float,
    blur_sigma: float,
    icon_path: str | None,
    render_scale: float = 0.5,
) -> None:
    """Capture one Wayland output via grim and apply all effects in a single pipeline.

    grim emits uncompressed PPM on stdout; ImageMagick reads it and writes the final PNG
    in one pass — no intermediate decode/encode of the full-size image.

    The image is rendered at ``render_scale`` of the output resolution (blur kernel and
    icon scaled to match) and swaylock stretches it back to full size. The image is
    pixelated/blurred anyway, so the quality loss is invisible while blur and PNG
    encoding run on a fraction of the pixels.
    """
    out_w = max(1, round(width * render_scale))
    out_h = max(1, round(height * render_scale))

    grim = subprocess.Popen(
        ["grim", "-t", "ppm", "-o", output_name, "-"],
        stdout=subprocess.PIPE,
    )
    convert_cmd: list[str] = [
        IM_BINARY,
        "ppm:-",
        "-scale",
        f"{pixelate_scale}%",
        "-scale",
        f"{out_w}x{out_h}!",
        "-blur",
        f"{blur_radius * render_scale:g},{blur_sigma * render_scale:g}",
    ]
    if icon_path:
        convert_cmd += [
            "(",
            icon_path,
            "-resize",
            f"{render_scale * 100:g}%",
            ")",
            "-gravity",
            "center",
            "-composite",
        ]
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


def pixelate_and_blur(
    image_path: str,
    scale_down: int = 10,
    radius: float = 2,
    sigma: float = 5,
) -> None:
    """Pixelate and blur an image in a single ImageMagick pass."""
    _convert(
        [
            image_path,
            "-scale",
            f"{scale_down}%",
            "-scale",
            "1000%",
            "-blur",
            f"{radius},{sigma}",
            image_path,
        ]
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
    """Detect connected displays and their geometry.

    Returns a list of dicts with keys: width, height, x, y.
    """
    displays: list[dict[str, int]] = []

    # Try wlr-randr first (wlroots compositors)
    try:
        result = subprocess.run(["wlr-randr"], capture_output=True, text=True, check=True)
        current_display: str | None = None
        geometry: dict[str, int] = {}

        for line in result.stdout.splitlines():
            stripped = line.strip()

            # Display header line (e.g., "DP-1 ...")
            if not line.startswith(" ") and not line.startswith("\t") and stripped:
                if current_display and geometry.get("width"):
                    displays.append(geometry)
                current_display = stripped.split()[0]
                geometry = {"width": 0, "height": 0, "x": 0, "y": 0}

            # Resolution line with "current"
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

            # Position line
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
        import re

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


def composite_icon(image_path: str, icon_path: str) -> None:
    """Overlay the lock icon centered on each detected display."""
    displays = _get_display_geometries()

    if not displays:
        # Fallback: center on single display
        _convert([image_path, icon_path, "-gravity", "center", "-composite", image_path])
        return

    # Get icon dimensions
    result = subprocess.run(
        ["identify", "-format", "%w %h", icon_path],
        capture_output=True,
        text=True,
        check=True,
    )
    icon_w, icon_h = (int(v) for v in result.stdout.strip().split())

    # Chain all composites in a single command: one decode/encode of the
    # full image instead of one per display.
    args: list[str] = [image_path, "-gravity", "NorthWest"]
    for display in displays:
        center_x = display["x"] + (display["width"] - icon_w) // 2
        center_y = display["y"] + (display["height"] - icon_h) // 2
        args += [icon_path, "-geometry", f"+{center_x}+{center_y}", "-composite"]
    args.append(image_path)
    _convert(args)
