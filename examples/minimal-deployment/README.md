# Minimal deployment

This deployment uses `backend_mode: mock`. It verifies Service registration and
lifecycle without importing PyTorch or loading a checkpoint. The mock capability
returns `success=false`, no action, and `fallback_required=true`.

```bash
rbnx build -f robonix_manifest.yaml
rbnx boot -f robonix_manifest.yaml
```

For a real deployment, configure `target_checkpoint`, `drafter_checkpoint`,
`allowed_image_root`, and `unnorm_key`, and choose the GPU with
`CUDA_VISIBLE_DEVICES` before boot.
