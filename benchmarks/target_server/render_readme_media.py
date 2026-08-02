#!/usr/bin/env python3
"""Render README result badges and cards without replacing the live demo."""

from __future__ import annotations

import argparse
import html
import json
import textwrap
from pathlib import Path

try:
    import imageio.v2 as imageio
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError as error:  # pragma: no cover - exercised by the documented CLI
    raise SystemExit(
        "Install README media dependencies first: "
        "python -m pip install 'Pillow>=10' 'imageio>=2.34' "
        "'imageio-ffmpeg>=0.5' 'numpy>=1.26'"
    ) from error


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUMMARY = Path(__file__).with_name("results") / "summary.json"
DEFAULT_RESEARCH_SUMMARY = ROOT / "benchmarks" / "research_results" / "summary.json"
DEFAULT_OUTPUT = ROOT / "docs" / "assets" / "readme"
CANVAS = (1440, 810)
FPS = 12


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for name in names:
        path = Path(name)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def base_slide(image_path: Path, title: str, subtitle: str) -> Image.Image:
    with Image.open(image_path) as source:
        canvas = ImageOps.fit(source.convert("RGB"), CANVAS, Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(CANVAS[1]):
        alpha = int(28 + 170 * (y / CANVAS[1]) ** 2)
        draw.line((0, y, CANVAS[0], y), fill=(3, 9, 24, alpha))
    draw.rounded_rectangle(
        (70, 590, 1370, 755),
        radius=22,
        fill=(4, 12, 32, 210),
        outline=(81, 189, 255, 160),
        width=2,
    )
    draw.text((110, 620), title, font=font(48, bold=True), fill=(238, 248, 255, 255))
    wrapped = textwrap.fill(subtitle, width=84)
    draw.multiline_text((112, 684), wrapped, font=font(25), fill=(172, 213, 239, 255), spacing=7)
    return Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")


def validation_slide(summary: dict) -> Image.Image:
    robonix = summary["routes"]["robonix_executor_mcp"]
    speedup = summary["speculative_speedup_p50"]
    peak_gpu = robonix["peak_gpu_memory_mib"]
    canvas = Image.new("RGB", CANVAS, "#071226")
    draw = ImageDraw.Draw(canvas)
    draw.text((80, 58), "Real RoboNix validation", font=font(54, bold=True), fill="#f1f7ff")
    draw.text((82, 128), "10 LIBERO-Goal observations · Executor → Atlas → MCP", font=font(27), fill="#8fd8ff")
    cards = [
        (str(robonix["calls"]), "full-chain calls", "#28b8ff"),
        (f'{summary["max_action_error"]:.1f}', "maximum action error", "#7dd3a7"),
        ("verified", "target-model fallback", "#a993ff"),
    ]
    for index, (value, label, color) in enumerate(cards):
        x = 80 + index * 440
        draw.rounded_rectangle((x, 195, x + 400, 365), radius=24, fill="#0e2140", outline=color, width=3)
        draw.text((x + 28, 225), value, font=font(48, bold=True), fill=color)
        draw.text((x + 28, 300), label, font=font(24), fill="#cfdeef")

    facts = [
        ("P50 wrapper overhead", f'{summary["service_wrapper_overhead_p50_ms"]:.2f} ms', "#28b8ff"),
        ("Measured P50 speedup", f"{speedup:.3f}×", "#ffc56e"),
        ("Peak GPU allocation", f"{peak_gpu:,} MiB", "#ff8e8e"),
    ]
    for index, (label, value, color) in enumerate(facts):
        x = 80 + index * 440
        draw.rounded_rectangle((x, 420, x + 400, 620), radius=24, fill="#0b1c38")
        draw.text((x + 28, 455), label, font=font(23), fill="#a9bed5")
        draw.text((x + 28, 510), value, font=font(46, bold=True), fill=color)
    draw.text(
        (80, 690),
        "1.034× is not a material speedup · 39,603 MiB is an explicit 40 GB deployment risk",
        font=font(27, bold=True),
        fill="#ffd7a0",
    )
    return canvas


def project_results_slide(research: dict) -> Image.Image:
    headline = research["headline"]
    canvas = Image.new("RGB", CANVAS, "#071226")
    draw = ImageDraw.Draw(canvas)
    draw.text((80, 62), "Kinematics-aware VLA acceleration", font=font(54, bold=True), fill="#f1f7ff")
    draw.text((82, 132), "Four LIBERO suites · target verification · motion-aware recovery", font=font(27), fill="#8fd8ff")
    cards = [
        (f'{headline["max_speedup"]:.2f}×', "peak end-to-end speedup", "#28b8ff"),
        (f'{headline["best_success_rate_pct"]:.1f}%', "best task success rate", "#7dd3a7"),
        (f'{headline["acceleration_over_speculative_baseline_min_pct"]}–{headline["acceleration_over_speculative_baseline_max_pct"]}%', "gain over speculative baseline", "#a993ff"),
    ]
    for index, (value, label, color) in enumerate(cards):
        x = 80 + index * 440
        draw.rounded_rectangle((x, 205, x + 400, 405), radius=24, fill="#0e2140", outline=color, width=3)
        draw.text((x + 28, 245), value, font=font(50, bold=True), fill=color)
        draw.text((x + 28, 330), label, font=font(23), fill="#cfdeef")
    draw.text((80, 500), "Draft fast · verify in parallel · compensate recoverable motion error · fall back safely", font=font(29, bold=True), fill="#dcecff")
    draw.text((80, 570), "The RoboNix Service packages this decision path as a reusable candidate-action capability.", font=font(27), fill="#9eb8d5")
    return canvas


def badge_svg(research: dict) -> str:
    headline = research["headline"]
    labels = (
        ("peak speedup", f'{headline["max_speedup"]:.2f}×'),
        ("best success rate", f'{headline["best_success_rate_pct"]:.1f}%'),
        ("baseline gain", f'{headline["acceleration_over_speculative_baseline_min_pct"]}–{headline["acceleration_over_speculative_baseline_max_pct"]}%'),
    )
    colors = ("#1677ff", "#16865c", "#6954d9")
    blocks = []
    for index, ((label, value), color) in enumerate(zip(labels, colors)):
        x = index * 320
        blocks.append(
            f'<g transform="translate({x},0)"><rect width="300" height="86" rx="16" fill="#0b1730" stroke="{color}" stroke-width="2"/>'
            f'<text x="24" y="33" fill="#9eb5ce" font-family="Arial,sans-serif" font-size="18">{html.escape(label)}</text>'
            f'<text x="24" y="66" fill="#f4f8ff" font-family="Arial,sans-serif" font-size="28" font-weight="700">{html.escape(value)}</text></g>'
        )
    return '<svg xmlns="http://www.w3.org/2000/svg" width="940" height="86" viewBox="0 0 940 86">' + "".join(blocks) + "</svg>\n"


def reel_frames(slides: list[Image.Image]) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for index, slide in enumerate(slides):
        frames.extend([slide] * 18)
        if index + 1 < len(slides):
            frames.extend(Image.blend(slide, slides[index + 1], step / 8) for step in range(1, 8))
    return frames


def write_video(frames: list[Image.Image], output: Path) -> None:
    writer = imageio.get_writer(output, fps=FPS, codec="libx264", quality=8, macro_block_size=1)
    try:
        for frame in frames:
            writer.append_data(np.asarray(frame))
    finally:
        writer.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--research-summary", type=Path, default=DEFAULT_RESEARCH_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    research = json.loads(args.research_summary.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    validation = args.output / "vla-validation-summary.webp"
    validation_slide(summary).save(validation, "WEBP", quality=90, method=6)
    (args.output / "result-badges.svg").write_text(badge_svg(research), encoding="utf-8")
    print(f"rendered README result cards in {args.output}; live demo media was not modified")


if __name__ == "__main__":
    main()
