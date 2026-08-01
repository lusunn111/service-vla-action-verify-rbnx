---
description: Return a candidate VLA action without commanding robot hardware.
---

# VLA action decision

## Public capability

`robonix/service/vla/action_decision/decide`

The Service accepts a language instruction, a deployment-owned local
observation image, and a timeout. It first attempts Drafter proposal plus target
verification and reuses the already-loaded target model for fallback.

`observation_uri` accepts an absolute local path or `file://` URI only. The
resolved image must stay below `allowed_image_root`, and its JPEG, PNG, or WebP
filename type must match its file signature. The returned action must match
`expected_action_dim` and contain finite numeric values.

## Lifecycle

RoboNix activation does not import PyTorch, allocate GPU memory, or load either
checkpoint. The first real `decide` call performs lazy loading, and subsequent
calls reuse the same model pair. Before loading, the Service checks the target
processor, dataset statistics, target weights, Drafter configuration, and the
weight filename required by serial or parallel draft mode.

If speculative inference fails while time remains, the already-loaded target
model runs the fallback path. If both paths fail, the Service drops both model
references and releases its CUDA cache so the next call starts from a clean
state.

`timeout_s` includes lazy loading and both inference paths. GPU kernels are not
forcefully interrupted; the deadline is enforced before target fallback and
after each non-preemptible model operation.

## Safety boundary

The response is a candidate action, not an execution authorization. The caller
must apply robot-specific normalization, joint limits, collision checks,
freshness checks, and any hardware interlock. Mock mode always returns
`success=false`, no action, and `fallback_required=true`.
