---
description: Return a candidate VLA action without commanding robot hardware.
---

# VLA action decision

## Public capability

`robonix/service/vla/action_decision/decide`

The Service accepts a language instruction, a deployment-owned local
observation image, and a timeout. It first attempts Drafter proposal plus target
verification and reuses the already-loaded target model for fallback.

## Lifecycle

RoboNix activation does not import PyTorch, allocate GPU memory, or load either
checkpoint. The first real `decide` call performs lazy loading, and subsequent
calls reuse the same model pair.

## Safety boundary

The response is a candidate action, not an execution authorization. The caller
must apply robot-specific normalization, joint limits, collision checks,
freshness checks, and any hardware interlock. Mock mode always returns
`success=false`, no action, and `fallback_required=true`.
