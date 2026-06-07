# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.0.0"]
# ///
"""Prepare Slack custom emoji assets.

Usage:
    uv run custom-slack-emojis/scripts/prepare_slack_emoji.py input.png --out-dir out --name try_it
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence


MAX_FRAMES_DEFAULT = 50
SIZES_TO_TRY = (128, 112, 96, 80, 64)


def fit_square(image: Image.Image, size: int) -> Image.Image:
    frame = ImageOps.exif_transpose(image).convert("RGBA")
    frame.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - frame.width) // 2
    y = (size - frame.height) // 2
    canvas.alpha_composite(frame, (x, y))
    return canvas


def sample_indices(count: int, limit: int) -> list[int]:
    if count <= limit:
        return list(range(count))
    return sorted({round(i * (count - 1) / (limit - 1)) for i in range(limit)})


def save_png(source: Image.Image, out_path: Path, max_bytes: int) -> dict:
    attempts = []
    for size in SIZES_TO_TRY:
        prepared = fit_square(source, size)
        prepared.save(out_path, format="PNG", optimize=True)
        byte_count = out_path.stat().st_size
        attempts.append({"size": size, "bytes": byte_count})
        if byte_count <= max_bytes:
            return {
                "path": str(out_path),
                "format": "PNG",
                "width": size,
                "height": size,
                "bytes": byte_count,
                "ok": True,
                "attempts": attempts,
            }
    return {
        "path": str(out_path),
        "format": "PNG",
        "width": SIZES_TO_TRY[-1],
        "height": SIZES_TO_TRY[-1],
        "bytes": out_path.stat().st_size,
        "ok": False,
        "reason": "file remains over max bytes",
        "attempts": attempts,
    }


def gif_frames(source: Image.Image, max_frames: int) -> tuple[list[Image.Image], list[int]]:
    all_frames = list(ImageSequence.Iterator(source))
    indices = sample_indices(len(all_frames), max_frames)
    frames = []
    durations = []
    for index in indices:
        frame = all_frames[index]
        frames.append(frame.copy())
        durations.append(int(frame.info.get("duration", source.info.get("duration", 80))))
    return frames, durations


def save_gif(source: Image.Image, out_path: Path, max_bytes: int, max_frames: int) -> dict:
    source_frames, durations = gif_frames(source, max_frames)
    attempts = []
    frame_limits = [len(source_frames)]
    if len(source_frames) > 24:
        frame_limits.append(24)
    if len(source_frames) > 16:
        frame_limits.append(16)
    if len(source_frames) > 10:
        frame_limits.append(10)

    for frame_limit in dict.fromkeys(frame_limits):
        frame_indices = sample_indices(len(source_frames), frame_limit)
        for size in SIZES_TO_TRY:
            frames = [fit_square(source_frames[i], size).convert("P", palette=Image.Palette.ADAPTIVE, colors=255) for i in frame_indices]
            frame_durations = [durations[i] for i in frame_indices]
            frames[0].save(
                out_path,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=frame_durations,
                loop=0,
                optimize=True,
                disposal=2,
            )
            byte_count = out_path.stat().st_size
            attempts.append({"size": size, "frames": len(frames), "bytes": byte_count})
            if byte_count <= max_bytes and len(frames) <= max_frames:
                return {
                    "path": str(out_path),
                    "format": "GIF",
                    "width": size,
                    "height": size,
                    "frames": len(frames),
                    "bytes": byte_count,
                    "ok": True,
                    "attempts": attempts,
                }

    return {
        "path": str(out_path),
        "format": "GIF",
        "bytes": out_path.stat().st_size,
        "ok": False,
        "reason": "gif remains over max bytes",
        "attempts": attempts,
    }


def output_name(input_path: Path, requested_name: str | None, index: int, total: int, suffix: str) -> str:
    stem = requested_name or input_path.stem.lower().replace(" ", "_")
    if total > 1:
        stem = f"{stem}-{index + 1:02d}"
    return f"{stem}{suffix}"


def process_one(input_path: Path, out_dir: Path, name: str | None, index: int, total: int, max_bytes: int, max_frames: int) -> dict:
    with Image.open(input_path) as source:
        is_gif = source.format == "GIF" and getattr(source, "is_animated", False)
        suffix = ".gif" if is_gif else ".png"
        out_path = out_dir / output_name(input_path, name, index, total, suffix)
        if is_gif:
            result = save_gif(source, out_path, max_bytes, max_frames)
        else:
            result = save_png(source, out_path, max_bytes)
    result["source"] = str(input_path)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Slack-ready custom emoji assets.")
    parser.add_argument("inputs", nargs="+", type=Path, help="Source image files.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory for processed emoji files.")
    parser.add_argument("--name", help="Output shortcode stem. For multiple inputs, -01, -02, etc. is appended.")
    parser.add_argument("--max-kb", type=int, default=128, help="Maximum output size in KB. Default: 128.")
    parser.add_argument("--max-frames", type=int, default=MAX_FRAMES_DEFAULT, help="Maximum GIF frames. Default: 50.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = args.max_kb * 1024

    results = [
        process_one(path, args.out_dir, args.name, index, len(args.inputs), max_bytes, args.max_frames)
        for index, path in enumerate(args.inputs)
    ]
    print(json.dumps(results, indent=2))
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
