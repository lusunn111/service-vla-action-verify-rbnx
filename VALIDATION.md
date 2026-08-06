# Target-server validation record

## Scope and result

Release candidate 0.1.0 was validated on 2026-08-01 through the real RoboNix
route:

```text
Executor -> Atlas -> MCP -> VLA action-verify Service
         -> repository-packaged OpenVLA/SpecVLA inference -> external checkpoints
```

The Service loaded inference source only from this repository. OpenVLA and
Drafter weights plus the LIBERO observations were external deployment assets
connected by checked symbolic links; they are not redistributed.

The validation passed:

- RoboNix boot registered the `verify` MCP capability without importing
  PyTorch or allocating GPU memory. GPU 1 remained at 3 MiB.
- The first Executor call lazily loaded the target OpenVLA and Drafter and
  returned a finite 7-dimensional candidate action in `speculative` mode.
- Thirty direct speculative calls and thirty Executor/MCP calls matched
  element-by-element: maximum action error `0.0`, with no parity failure.
- The benchmark harness injected a Drafter exception after real model loading.
  The production backend returned a real target-model action in
  `target_fallback` mode with `fallback_used=true`.
- Shutdown removed the Service, Executor, and Atlas processes. GPU 1 returned
  to 3 MiB and no validation port remained open.

During validation, target-only fallback exposed retained speculative
`tree_mask` state in the preserved research code. The Service now clears
request-local tree state before target decoding; both the full direct benchmark
and the fault-injected fallback passed after this fix.

## Environment

| Item | Validated value |
| --- | --- |
| Date | 2026-08-01 |
| Operating system | Ubuntu 22.04.5 LTS, Linux 5.15.0-179-generic |
| GPU | NVIDIA A100-PCIE-40GB on GPU 1, driver 550.54.14 |
| Service Python | 3.10.19 in a dedicated environment |
| PyTorch / CUDA | PyTorch 2.2.0+cu121 |
| Transformers | 4.40.1 |
| FastMCP | 3.4.4 |
| RoboNix | 0.1.0, commit `48af09190b99f7847dddf68457eec2db42d2c1a7` |
| Input set | 10 real LIBERO-Goal observations |
| Repetition | one warm-up followed by three measured calls per case and route |

The compatibility environment variable
`PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` is set by the Service start
script because the preserved TensorFlow/TFDS stack and RoboNix-generated gRPC
code require different Protobuf APIs.

## Benchmark result

| Route | Calls | Mean | P50 | P95 |
| --- | ---: | ---: | ---: | ---: |
| Direct target-only | 30 | 179.31 ms | 178.95 ms | 181.03 ms |
| Direct speculative | 30 | 176.12 ms | 173.00 ms | 202.72 ms |
| Executor -> Atlas -> MCP | 30 | 187.45 ms | 182.88 ms | 212.10 ms |

Model construction took 12.64 s. The first full Service call took 13.98 s, and
the P50 Service wrapping overhead was 9.88 ms. The measured target-to-
speculative P50 speedup was only 1.034x on this input set and configuration;
this is a functional release benchmark, not evidence of a material speedup.

The model occupied 15,329 MiB immediately after loading. The process-level peak
reported by `nvidia-smi` reached 39,603 MiB after image preprocessing because
the preserved TensorFlow stack reserved most remaining GPU memory. This number
is not model-weight size and is a deployment risk on a 40GB GPU.

![VLA action-verify latency](benchmarks/target_server/results/latency.svg)

Raw calls, cold-start data, fault-injection evidence, summary, input provenance
hashes, and the deterministic chart are committed under
`benchmarks/target_server/`.

## Safety and reporting boundary

The capability returns candidate actions only. It never sends commands to
robot hardware; downstream collision, workspace, rate, and task-state checks
remain mandatory. Mock mode cannot return a successful executable action.
Local images must remain under the configured root and pass size, extension,
signature, pixel-count, action-shape, and finite-value checks.

This benchmark proves deployment, lazy loading, deterministic action parity,
fallback, and lifecycle cleanup. It does not reproduce the paper's LIBERO
success rates, acceptance distributions, or end-to-end robot speedups.
