"""CLI entry point for lock-screen."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lock_screen.effects import blur, composite_icon, pixelate, process_output_fast
from lock_screen.locker import get_wayland_outputs, lock, lock_per_output
from lock_screen.screenshot import capture

DEFAULT_ICON = Path(__file__).resolve().parent.parent.parent / "lock.png"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lock-screen",
        description="Lock screen with blurred/pixelated screenshot background",
    )
    parser.add_argument(
        "--icon",
        type=Path,
        default=DEFAULT_ICON,
        help="Path to the lock icon image (default: lock.png in project root)",
    )
    parser.add_argument(
        "--pixelate-scale",
        type=int,
        default=10,
        help="Pixelation scale-down percentage (default: 10)",
    )
    parser.add_argument(
        "--blur-radius",
        type=float,
        default=2,
        help="Blur radius (default: 2)",
    )
    parser.add_argument(
        "--blur-sigma",
        type=float,
        default=5,
        help="Blur sigma (default: 5)",
    )
    parser.add_argument(
        "--no-icon",
        action="store_true",
        help="Skip overlaying the lock icon",
    )
    return parser.parse_args(argv)


def _try_fast_path(args: argparse.Namespace) -> bool:
    """Per-output parallel pipeline. Wayland + grim + swaylock only.

    Each monitor: grim -t ppm | convert (scale+blur+resize+composite) -> small PNG.
    All monitors run in parallel threads. Final swaylock call uses -i NAME:PATH.
    """
    if os.environ.get("XDG_SESSION_TYPE", "") != "wayland":
        return False
    if shutil.which("grim") is None or shutil.which("swaylock") is None:
        return False

    outputs = get_wayland_outputs()
    if not outputs:
        return False

    icon_path: str | None = None
    if not args.no_icon and args.icon.is_file():
        icon_path = str(args.icon)

    temp_dir = tempfile.mkdtemp(prefix="lock-screen-")
    try:
        def _process(o: dict[str, int | str]) -> tuple[str, str] | None:
            name = str(o["name"])
            width = int(o["width"])
            height = int(o["height"])
            out_path = os.path.join(temp_dir, f"{name}.png")
            try:
                process_output_fast(
                    output_name=name,
                    width=width,
                    height=height,
                    output_path=out_path,
                    pixelate_scale=args.pixelate_scale,
                    blur_radius=args.blur_radius,
                    blur_sigma=args.blur_sigma,
                    icon_path=icon_path,
                )
            except Exception as e:
                print(f"Warning: fast path failed for {name}: {e}", file=sys.stderr)
                return None
            if not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
                return None
            return name, out_path

        with ThreadPoolExecutor(max_workers=len(outputs)) as pool:
            results = list(pool.map(_process, outputs))

        if any(r is None for r in results):
            return False

        images = dict(r for r in results if r)
        lock_per_output(images)
        return True
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    if os.environ.get("LOCK_SCREEN_DEBUG", "False").lower() == "true":
        import debugpy
        debugpy.listen(("localhost", 5678))
        print("Waiting for debugger to attach on port 5678...")
        debugpy.wait_for_client()
        print("Debugger attached, continuing execution.")

    # Fast path: parallel per-output capture+process pipeline.
    if _try_fast_path(args):
        return

    # Fallback: single full-screen capture + sequential effects.
    fd, img_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)

    try:
        if not capture(img_path):
            print(
                "Error: Failed to capture screenshot. Install one of:\n"
                "  COSMIC/wlroots: sudo apt install grim\n"
                "  GNOME:          sudo apt install gnome-screenshot\n"
                "  KDE:            sudo apt install spectacle\n"
                "  X11:            sudo apt install scrot",
                file=sys.stderr,
            )
            sys.exit(1)

        pixelate(img_path, scale_down=args.pixelate_scale)
        blur(img_path, radius=args.blur_radius, sigma=args.blur_sigma)

        if not args.no_icon and args.icon.is_file():
            composite_icon(img_path, str(args.icon))

        lock(img_path)
    finally:
        if os.path.exists(img_path):
            os.remove(img_path)


if __name__ == "__main__":
    main()
