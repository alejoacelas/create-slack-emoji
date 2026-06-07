# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.0.0"]
# ///
"""Slice a 3x2 contact sheet into five candidate source images."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Slice a 3x2 Slack emoji contact sheet into five cells.")
    parser.add_argument("input", type=Path, help="Contact sheet image.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory for sliced cells.")
    parser.add_argument("--prefix", required=True, help="Output filename prefix.")
    parser.add_argument("--cols", type=int, default=3, help="Grid columns. Default: 3.")
    parser.add_argument("--rows", type=int, default=2, help="Grid rows. Default: 2.")
    parser.add_argument("--count", type=int, default=5, help="Number of cells to export. Default: 5.")
    parser.add_argument("--inset", type=float, default=0.08, help="Fractional crop inset per cell. Default: 0.08.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(args.input) as image:
        source = image.convert("RGBA")
        cell_w = source.width / args.cols
        cell_h = source.height / args.rows
        for index in range(args.count):
            col = index % args.cols
            row = index // args.cols
            inset_x = cell_w * args.inset
            inset_y = cell_h * args.inset
            box = (
                round(col * cell_w + inset_x),
                round(row * cell_h + inset_y),
                round((col + 1) * cell_w - inset_x),
                round((row + 1) * cell_h - inset_y),
            )
            cell = source.crop(box)
            out_path = args.out_dir / f"{args.prefix}-{index + 1:02d}.png"
            cell.save(out_path, format="PNG", optimize=True)
            print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
