# Validation record

This file separates code-completeness validation from GPU deployment
validation.

## Automated validation scope

- GitHub Actions runs unit tests on Python 3.10, 3.11, and 3.12.
- Activation without importing PyTorch, TensorFlow, or Transformers.
- Non-executable mock behavior.
- Lazy adapter loading, speculative success, target-model fallback, deadline
  handling, dual-failure cleanup, and deactivation cleanup with test adapters.
- Local-path containment, image signature and size checks.
- Checkpoint-layout, dataset-statistics key, action dimension, finite-value,
  instruction, GPU-selection, and timeout validation.
- Release audit, source distribution, Wheel runtime-content audit,
  `rbnx validate .`, and `rbnx build -p .`.

## Latest local run

On 2026-07-31, Python 3.13 ran 24 unit tests, the release audit, source and
Wheel builds, an isolated Wheel install and runtime-source discovery check,
shell syntax checks, bytecode compilation, and `git diff --check`. RoboNix CLI
validation is delegated to the GitHub Actions job because the local
workstation does not have `rbnx` installed. No GPU model was loaded.

## Deliberately not claimed

This release-preparation round did not load the 15GB OpenVLA checkpoint or
4.3GB Drafter on `target-server`, compare output with the direct research
script, measure GPU memory, or perform an Atlas/MCP deployment invocation.
Those checks remain required before merging, tagging `v0.1.0`, and submitting a
Catalog PR.
