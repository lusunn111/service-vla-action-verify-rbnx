# Real RoboNix deployment

This service-only deployment starts Atlas, Executor, and this published
Service. It omits Pilot, Liaison, Soma, and robot hardware. The first real
`verify` call loads the repository's packaged OpenVLA/SpecVLA implementation;
only model checkpoints and observations are external assets.

Copy `.env.example` to an untracked `.env`, replace every absolute path, then:

```bash
set -a
source .env
set +a

rbnx build -f robonix_manifest.yaml
rbnx boot -v -f robonix_manifest.yaml
```

Before the first call, verify that the Service PID is absent from the GPU
process list. In another terminal, load the same `.env` and call through the
real Executor path:

```bash
rbnx caps -v --server 127.0.0.1:50351
rbnx tools --server 127.0.0.1:50351
python ../../benchmarks/target_server/invoke_executor.py \
  --atlas 127.0.0.1:50351 \
  --provider vla_action_verify \
  --contract robonix/service/vla/action_verify/verify \
  --args-json '{"instruction":"pick up the bowl","observation_uri":"/absolute/path/observation.png","timeout_s":600}' \
  --timeout-s 900
```

Shut down only this deployment:

```bash
rbnx shutdown -f robonix_manifest.yaml
```

After shutdown, verify that the Service process and its GPU allocation are gone.
