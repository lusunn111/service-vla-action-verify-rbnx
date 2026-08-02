#!/usr/bin/env python3
"""Place one real rollout beside a directly time-scaled copy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _font(size: int, bold: bool = False):
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = Path("/usr/share/fonts/truetype/dejavu") / filename
    return ImageFont.truetype(path, size) if path.is_file() else ImageFont.load_default()


def _panel(image: Image.Image, label: str, finished: bool) -> Image.Image:
    panel = image.resize((600, 600), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(panel)
    draw.rectangle((0, 0, 600, 58), fill=(4, 12, 24, 220))
    draw.text((22, 16), label, font=_font(23, True), fill="#f8fafc")
    if finished:
        draw.rounded_rectangle((438, 13, 578, 47), radius=17, fill="#059669")
        draw.text((465, 20), "SUCCESS", font=_font(15, True), fill="white")
    return panel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--speedup", type=float, default=1.57)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--hold-s", type=float, default=2.0)
    args = parser.parse_args()
    if args.speedup <= 1 or args.fps <= 0 or args.hold_s < 0:
        raise SystemExit("speedup, fps, or hold-s is outside the allowed range")
    paths = sorted(args.observations.glob("step-*.jpg"))
    if not paths:
        raise SystemExit("no rollout observations found")
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    if not summary.get("success"):
        raise SystemExit("comparison video requires a successful real rollout")
    frames = [Image.open(path).convert("RGB") for path in paths]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(
        args.output, fps=args.fps, codec="libx264", quality=8, macro_block_size=None
    )
    try:
        total = len(frames) + round(args.hold_s * args.fps)
        for index in range(total):
            baseline_index = min(index, len(frames) - 1)
            accelerated_index = min(round(index * args.speedup), len(frames) - 1)
            canvas = Image.new("RGB", (1200, 664), "#07111f")
            canvas.paste(
                _panel(frames[baseline_index], "Baseline · 1.00×", baseline_index == len(frames) - 1),
                (0, 64),
            )
            canvas.paste(
                _panel(
                    frames[accelerated_index],
                    f"Accelerated · {args.speedup:.2f}×",
                    accelerated_index == len(frames) - 1,
                ),
                (600, 64),
            )
            draw = ImageDraw.Draw(canvas)
            draw.text((24, 18), "open the middle drawer of the cabinet", font=_font(23, True), fill="#f8fafc")
            draw.text((862, 22), "same real rollout · right side time-scaled", font=_font(14), fill="#94a3b8")
            writer.append_data(np.asarray(canvas))
    finally:
        writer.close()
        for frame in frames:
            frame.close()
    print(args.output)


if __name__ == "__main__":
    main()
