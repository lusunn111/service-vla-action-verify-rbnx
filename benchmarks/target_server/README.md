# Target-server benchmark

This benchmark has four explicit phases so the target model is never loaded by
two validation processes at once. Checkpoints and LIBERO images remain external
assets and are not redistributed.

## Asset layout and safe links

The validation host used `/data/zhihao/robonix-service` for assets,
environments, caches, runtime files, and validation outputs. Existing target
and Drafter checkpoints were linked without copying:

```bash
ASSET_ROOT=/data/zhihao/robonix-service/assets
LINK_SOURCE=/path/to/existing/openvla-libero-goal
LINK_TARGET="$ASSET_ROOT/openvla-libero-goal"

test -e "$LINK_SOURCE"
resolved_source="$(readlink -f "$LINK_SOURCE")"
if test -e "$LINK_TARGET" || test -L "$LINK_TARGET"; then
  test "$(readlink -f "$LINK_TARGET")" = "$resolved_source"
else
  ln -s "$resolved_source" "$LINK_TARGET"
fi
```

Repeat for the Drafter and dataset. Do not use `ln -sfn`, overwrite an
existing target, move shared assets, or commit a symbolic link.

## Phases

1. `direct` lazily loads this repository's packaged inference source and
   measures target-only and speculative calls.
2. `service` measures the complete Executor -> Atlas -> MCP -> Service route.
   Before its first call, verify the Service process has not mapped PyTorch and
   the selected GPU is idle.
3. `fallback` injects a Drafter exception in the benchmark harness after real
   model loading and verifies production target-model fallback. It adds no test
   switch to the public capability.
4. `summary` checks direct/Service action parity, writes the combined
   `calls.csv`, and emits `summary.json`. `render_results.py` rebuilds the
   SVG chart deterministically.

Representative commands:

```bash
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
export VLA_TARGET_CHECKPOINT="$ASSET_ROOT/openvla-libero-goal"
export VLA_DRAFTER_CHECKPOINT="$ASSET_ROOT/drafter-libero-goal"

python run_benchmark.py direct \
  --input-root "$VALIDATION_ROOT/inputs/vla" \
  --target-checkpoint "$VLA_TARGET_CHECKPOINT" \
  --drafter-checkpoint "$VLA_DRAFTER_CHECKPOINT" \
  --gpu-index 1 --warmup 1 --repeats 3 --output-dir results

# Boot examples/real-deployment/robonix_manifest.yaml before this phase.
python run_benchmark.py service \
  --input-root "$VALIDATION_ROOT/inputs/vla" \
  --target-checkpoint "$VLA_TARGET_CHECKPOINT" \
  --drafter-checkpoint "$VLA_DRAFTER_CHECKPOINT" \
  --gpu-index 1 --atlas 127.0.0.1:50351 \
  --provider vla_action_decision \
  --warmup 1 --repeats 3 --output-dir results

rbnx shutdown -f ../../examples/real-deployment/robonix_manifest.yaml

python run_benchmark.py fallback \
  --input-root "$VALIDATION_ROOT/inputs/vla" \
  --target-checkpoint "$VLA_TARGET_CHECKPOINT" \
  --drafter-checkpoint "$VLA_DRAFTER_CHECKPOINT" \
  --gpu-index 1 --output-dir results

python run_benchmark.py summary --output-dir results
python render_results.py
```

## Real RoboNix rollout video

`run_robonix_rollout.py` runs a LIBERO environment while keeping policy
inference inside the booted Service. For every policy step it writes the current
observation under the configured local-image root, submits a one-node plan to
Executor, validates the returned action shape, applies the candidate action to
the simulator, and appends an annotated frame to an H.264 MP4.

```bash
export PYTHONPATH="/path/to/LIBERO:$PYTHONPATH"
export MUJOCO_GL=egl

python run_robonix_rollout.py \
  --atlas 127.0.0.1:50351 \
  --provider vla_action_decision \
  --output-dir "$VALIDATION_ROOT/vla-rollout" \
  --task-suite libero_goal --task-id 0 --initial-state 0 \
  --wait-steps 10 --max-steps 300 --timeout-s 600 --fps 30
```

The committed demonstration completed “open the middle drawer of the cabinet”
in 120 policy steps. Its complete RoboNix route took 42.64 seconds;
`results/rollout-summary.json` is the sanitized summary. It is a simulator
success, not a physical-robot result.

The README comparison is deliberately simple: `render_speed_comparison.py`
places the captured motion sequence on the left and a direct 1.57× time-scaled
copy on the right. It does not claim two separately timed executions.

```bash
python render_speed_comparison.py \
  --observations "$VALIDATION_ROOT/vla-rollout/observations" \
  --summary results/rollout-summary.json \
  --output "$VALIDATION_ROOT/vla-speed-comparison.mp4" \
  --speedup 1.57 --fps 30
```

The committed input manifest contains only case identifiers, instructions,
record provenance, and SHA-256 hashes. The benchmark validates functional
parity, fallback, lazy loading, latency, GPU allocation, and cleanup; it is not
a LIBERO task-success evaluation. See `metadata.yaml`,
`results/summary.json`, and the repository-level `VALIDATION.md`.
