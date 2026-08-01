#!/usr/bin/env python3
"""Render committed VLA latency summaries as a deterministic SVG."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, default=Path(__file__).with_name("results") / "summary.json")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("results") / "latency.svg")
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    routes = summary["routes"]
    labels = [
        ("Target P50", routes["direct_target"]["p50_ms"]),
        ("Speculative P50", routes["direct_speculative"]["p50_ms"]),
        ("RoboNix P50", routes["robonix_executor_mcp"]["p50_ms"]),
    ]
    maximum = max(value for _, value in labels) or 1.0
    bars = []
    for index, (label, value) in enumerate(labels):
        x = 100 + index * 180
        height = 210 * value / maximum
        y = 260 - height
        bars.append(f'<rect x="{x}" y="{y:.2f}" width="105" height="{height:.2f}" fill="#7c3aed"/><text x="{x + 52}" y="{y - 8:.2f}" text-anchor="middle" font-size="13">{value:.2f} ms</text><text x="{x + 52}" y="286" text-anchor="middle" font-size="12">{label}</text>')
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="680" height="320" viewBox="0 0 680 320"><rect width="680" height="320" fill="white"/><text x="340" y="28" text-anchor="middle" font-family="sans-serif" font-size="18">VLA action-decision latency</text><line x1="55" y1="260" x2="635" y2="260" stroke="#111"/>' + "".join(bars) + "</svg>\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
