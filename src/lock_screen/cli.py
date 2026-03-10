"""CLI entry point for lock-screen."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from lock_screen.effects import blur, composite_icon, pixelate
from lock_screen.locker import lock
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


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    fd, img_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)

    try:
        # Capture screenshot
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

        # Apply effects
        pixelate(img_path, scale_down=args.pixelate_scale)
        blur(img_path, radius=args.blur_radius, sigma=args.blur_sigma)

        # Overlay icon
        if not args.no_icon and args.icon.is_file():
            composite_icon(img_path, str(args.icon))

        # Lock
        lock(img_path)
    finally:
        if os.path.exists(img_path):
            os.remove(img_path)


if __name__ == "__main__":
    main()
