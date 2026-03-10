"""Image effects: pixelation, blur, and lock icon compositing."""

from __future__ import annotations

import json
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

    # Fallback: macOS system_profiler
    if platform.system() == "Darwin":
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
                        # Fall back to logical resolution
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
            if displays:
                return displays
        except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
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
