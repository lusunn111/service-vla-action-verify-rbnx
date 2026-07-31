# Minimal deployment

This deployment uses `backend_mode: mock`. It verifies Service registration and
lifecycle without importing PyTorch or loading a checkpoint. The mock capability
returns `success=false`, no action, and `fallback_required=true`.

```bash
rbnx build -f robonix_manifest.yaml
rbnx boot -f robonix_manifest.yaml
```

For a real deployment, configure `target_checkpoint`, `drafter_checkpoint`,
`allowed_image_root`, and `unnorm_key`. A complete Service entry is:

```yaml
service:
  - name: vla_action_decision
    path: ../..
    config:
      backend_mode: openvla
      target_checkpoint: /absolute/path/to/openvla
      drafter_checkpoint: /absolute/path/to/drafter
      allowed_image_root: /absolute/path/to/robot-observations
      cuda_visible_devices: "1"
      require_cuda: true
      unnorm_key: libero_goal
      expected_action_dim: 7
      max_timeout_s: 300
```

The first real `decide` call validates the checkpoint layout and then loads the
target model and Drafter. `cuda_visible_devices: "1"` exposes physical GPU 1 as
logical `cuda:0` before PyTorch is imported.

Install the real inference dependencies in a Python 3.10 or 3.11 environment:

```bash
python -m pip install -e '.[inference]'
export ROBONIX_SERVICE_PYTHON=/absolute/path/to/inference-env/bin/python
```

The request timeout is checked before loading, after loading, and after each
non-preemptible GPU inference boundary. If the speculative path fails before
the deadline, the already-loaded target model is reused. If both paths fail or
the deadline expires, the model references and package-owned CUDA cache are
released. See [`VALIDATION.md`](../../VALIDATION.md) for the remaining
real-GPU deployment gate.
