#!/usr/bin/env python3
"""Extract deterministic LIBERO-Goal observations from local RLDS shards."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


DATASET_NAME = "libero_goal_no_noops"


def extract(dataset_root: Path, output_root: Path, case_count: int) -> dict:
    import tensorflow as tf

    directory = dataset_root / DATASET_NAME / "1.0.0"
    shards = sorted(directory.glob("*.tfrecord-*"))
    if not shards:
        raise FileNotFoundError(f"no TFRecord shards under {directory}")
    output_root.mkdir(parents=True, exist_ok=True)
    cases = []
    for shard in shards:
        dataset = tf.data.TFRecordDataset([str(shard)], num_parallel_reads=1)
        for record_index, raw in enumerate(dataset):
            episode = tf.train.Example.FromString(bytes(raw.numpy()))
            feature = episode.features.feature
            instructions = feature["steps/language_instruction"].bytes_list.value
            images = feature["steps/observation/image"].bytes_list.value
            step_count = min(len(instructions), len(images))
            if step_count == 0:
                continue
            step_index = step_count // 2
            image = bytes(images[step_index])
            if len(image) < 4 or not image.startswith(b"\xff\xd8\xff"):
                raise ValueError("observation is not a JPEG image")
            case_id = f"goal-{len(cases):02d}"
            image_path = output_root / f"{case_id}.jpg"
            image_path.write_bytes(image)
            cases.append(
                {
                    "case_id": case_id,
                    "instruction": bytes(instructions[step_index]).decode("utf-8").strip(),
                    "observation": image_path.name,
                    "observation_sha256": hashlib.sha256(image).hexdigest(),
                    "source": {
                        "dataset": DATASET_NAME,
                        "shard": shard.name,
                        "record_index": record_index,
                        "step_index": step_index,
                    },
                }
            )
            if len(cases) == case_count:
                return {
                    "schema_version": 1,
                    "description": "Real LIBERO-Goal observations are extracted from licensed assets and are not redistributed.",
                    "cases": cases,
                }
    raise RuntimeError(f"extracted {len(cases)} cases, expected {case_count}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--case-count", type=int, default=10)
    args = parser.parse_args()
    if args.case_count <= 0:
        raise SystemExit("--case-count must be positive")
    if args.output_root.exists() and any(args.output_root.iterdir()):
        raise SystemExit("--output-root must be empty to prevent mixed validation inputs")
    manifest = extract(args.dataset_root.resolve(), args.output_root.resolve(), args.case_count)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"extracted {len(manifest['cases'])} cases to {args.output_root}")


if __name__ == "__main__":
    main()
