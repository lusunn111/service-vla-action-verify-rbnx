#!/usr/bin/env python3
"""Run one LIBERO rollout through Executor -> Atlas -> MCP -> this Service."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from executor_client import ExecutorClient


CONTRACT = "robonix/service/vla/action_decision/decide"


def _font(size: int, bold: bool = False):
    names = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    )
    for name in names:
        if Path(name).is_file():
            return ImageFont.truetype(name, size=size)
    return ImageFont.load_default()


def _wrapped(draw: ImageDraw.ImageDraw, text: str, width: int, font) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _render_frame(
    observation: np.ndarray,
    *,
    instruction: str,
    step: int,
    max_steps: int,
    latency_ms: float,
    mode: str,
    action: np.ndarray,
    done: bool,
) -> np.ndarray:
    canvas = Image.new("RGB", (1280, 720), "#07111f")
    sim = Image.fromarray(observation).resize((720, 720), Image.Resampling.LANCZOS)
    canvas.paste(sim, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 720, 82), fill=(4, 12, 24, 220))
    draw.text((28, 20), "RoboNix · LIVE LIBERO ROLLOUT", font=_font(26, True), fill="#f8fafc")
    draw.text((28, 52), "Executor → Atlas → MCP → VLA Service", font=_font(17), fill="#67e8f9")

    left = 760
    draw.text((left, 42), "VLA Action Decision", font=_font(32, True), fill="#f8fafc")
    draw.text((left, 88), "IFLab · Peking University", font=_font(18), fill="#94a3b8")
    draw.line((left, 126, 1232, 126), fill="#1e3a5f", width=2)

    label_font = _font(15, True)
    body_font = _font(20)
    draw.text((left, 158), "TASK INSTRUCTION", font=label_font, fill="#67e8f9")
    y = 190
    for line in _wrapped(draw, instruction, 458, body_font):
        draw.text((left, y), line, font=body_font, fill="#e2e8f0")
        y += 29

    y = max(y + 20, 300)
    values = (
        ("POLICY STEP", f"{step:03d} / {max_steps}"),
        ("INFERENCE MODE", mode),
        ("MCP LATENCY", f"{latency_ms:.1f} ms"),
        ("TASK STATE", "SUCCESS" if done else "RUNNING"),
    )
    for label, value in values:
        draw.text((left, y), label, font=label_font, fill="#64748b")
        color = "#34d399" if label == "TASK STATE" and done else "#f8fafc"
        draw.text((1010, y - 4), value, font=_font(19, True), fill=color)
        y += 44

    draw.text((left, y + 12), "CANDIDATE ACTION", font=label_font, fill="#67e8f9")
    y += 48
    labels = ("x", "y", "z", "rx", "ry", "rz", "grip")
    for index, (name, value) in enumerate(zip(labels, action.tolist())):
        row = index // 4
        column = index % 4
        x = left + column * 116
        yy = y + row * 62
        draw.rounded_rectangle((x, yy, x + 102, yy + 46), radius=8, fill="#0f2238", outline="#234569")
        draw.text((x + 8, yy + 7), name, font=_font(13, True), fill="#94a3b8")
        draw.text((x + 36, yy + 7), f"{value:+.3f}", font=_font(14), fill="#e2e8f0")

    draw.text((760, 687), "Simulation only · candidate actions are not sent to physical hardware", font=_font(14), fill="#64748b")
    return np.asarray(canvas)


def _policy_action(output: dict) -> np.ndarray:
    horizon = int(output["action_horizon"])
    dimension = int(output["action_dim"])
    values = np.asarray(output["actions"], dtype=np.float64)
    if horizon <= 0 or dimension != 7 or values.size != horizon * dimension:
        raise RuntimeError("Service returned an invalid action shape")
    if not np.isfinite(values).all():
        raise RuntimeError("Service returned a non-finite action")
    action = values.reshape(horizon, dimension)[0].copy()
    action[-1] = -np.sign(2.0 * action[-1] - 1.0)
    return action


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atlas", default="127.0.0.1:50351")
    parser.add_argument("--provider", default="vla_action_decision")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--task-suite", default="libero_goal")
    parser.add_argument("--task-id", type=int, default=0)
    parser.add_argument("--initial-state", type=int, default=0)
    parser.add_argument("--wait-steps", type=int, default=10)
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--timeout-s", type=float, default=600.0)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    if args.max_steps <= 0 or args.wait_steps < 0 or args.fps <= 0:
        raise SystemExit("step counts and fps are outside the allowed range")

    from libero.libero import benchmark, get_libero_path
    from libero.libero.envs import OffScreenRenderEnv

    np.random.seed(7)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    observations = args.output_dir / "observations"
    observations.mkdir(exist_ok=True)
    calls_path = args.output_dir / "calls.jsonl"
    video_path = args.output_dir / "vla-robonix-rollout.mp4"

    suite = benchmark.get_benchmark_dict()[args.task_suite]()
    if not 0 <= args.task_id < suite.n_tasks:
        raise SystemExit("task-id is outside the selected suite")
    task = suite.get_task(args.task_id)
    initial_states = suite.get_task_init_states(args.task_id)
    if not 0 <= args.initial_state < len(initial_states):
        raise SystemExit("initial-state is outside the selected task")
    bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
    env = OffScreenRenderEnv(
        bddl_file_name=str(bddl), camera_heights=256, camera_widths=256
    )
    env.seed(0)
    env.reset()
    observation = env.set_init_state(initial_states[args.initial_state])
    for _ in range(args.wait_steps):
        observation, _, _, _ = env.step([0, 0, 0, 0, 0, 0, -1])

    client = ExecutorClient(args.atlas, args.timeout_s)
    records: list[dict] = []
    success = False
    started = time.time()
    writer = imageio.get_writer(
        video_path, fps=args.fps, codec="libx264", quality=8, macro_block_size=None
    )
    try:
        with calls_path.open("w", encoding="utf-8") as calls:
            for step in range(args.max_steps):
                image = observation["agentview_image"][::-1, ::-1].copy()
                image_path = observations / f"step-{step:04d}.jpg"
                Image.fromarray(image).save(image_path, format="JPEG", quality=95)
                result = client.call(
                    args.provider,
                    CONTRACT,
                    {
                        "instruction": task.language,
                        "observation_uri": str(image_path.resolve()),
                        "timeout_s": args.timeout_s,
                    },
                )
                action = _policy_action(result.output)
                observation, reward, done, info = env.step(action.tolist())
                success = bool(done)
                record = {
                    "step": step,
                    "plan_id": result.plan_id,
                    "elapsed_ms": result.elapsed_ms,
                    "mode": result.output.get("mode"),
                    "fallback_used": result.output.get("fallback_used"),
                    "action": action.tolist(),
                    "reward": float(reward),
                    "done": success,
                }
                records.append(record)
                calls.write(json.dumps(record, sort_keys=True) + "\n")
                calls.flush()
                frame = _render_frame(
                    image,
                    instruction=task.language,
                    step=step + 1,
                    max_steps=args.max_steps,
                    latency_ms=result.elapsed_ms,
                    mode=str(result.output.get("mode", "unknown")),
                    action=action,
                    done=success,
                )
                writer.append_data(frame)
                if success:
                    for _ in range(args.fps * 2):
                        writer.append_data(frame)
                    break
    finally:
        writer.close()
        client.close()
        env.close()

    latencies = [record["elapsed_ms"] for record in records]
    ordered = sorted(latencies)
    summary = {
        "schema_version": 1,
        "route": "Executor -> Atlas -> MCP -> vla_action_decision",
        "task_suite": args.task_suite,
        "task_id": args.task_id,
        "initial_state": args.initial_state,
        "instruction": task.language,
        "success": success,
        "policy_steps": len(records),
        "wall_time_s": time.time() - started,
        "latency_mean_ms": sum(latencies) / len(latencies),
        "latency_p50_ms": ordered[math.floor((len(ordered) - 1) * 0.50)],
        "latency_p95_ms": ordered[math.floor((len(ordered) - 1) * 0.95)],
        "video": video_path.name,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
