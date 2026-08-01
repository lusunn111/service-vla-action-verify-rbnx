<div align="center">

# RoboNix VLA Action Decision Service

**A system-level action decision, speculative verification, and target-model fallback Service for embodied models**

[中文文档](README-CN.md) · [🚀 Quick Start](#quick-start) · [⚙️ Requirements](#requirements) · [🧪 Validation](#validated-release) · [📝 Citation](#citation)

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-2.2-EE4C2C?logo=pytorch&logoColor=white)
![CUDA](https://img.shields.io/badge/CUDA-12.1-76B900?logo=nvidia&logoColor=white)
![LIBERO](https://img.shields.io/badge/LIBERO-rollout_verified-1f9d72)
[![License](https://img.shields.io/badge/license-MulanPSL--2.0-red)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/lusunn111/service-vla-action-decision-rbnx?style=flat&logo=github)](https://github.com/lusunn111/service-vla-action-decision-rbnx/stargazers)

</div>

The **RoboNix VLA Action Decision Service** lets
existing Vision-Language-Action (VLA) models verify low-cost action proposals
with both the target model and motion priors before execution. Adaptive
acceptance, motion compensation, and policy fallback reduce repeated large-model
inference while preserving task-level reliability. The research implementation currently supports
OpenVLA with Drafter-based proposals, parallel verification, motion-aware
compensation, and original-policy fallback.

## RoboNix Service package

The repository root is directly publishable as
`robonix.service.vla.action_decision`. It exposes
`robonix/service/vla/action_decision/decide`, returns candidate actions only,
and never commands robot hardware. RoboNix activation does not import PyTorch
or allocate GPU memory; the target model and Drafter load on the first real
request.

For repository checks:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/release_audit.py
python -m build
python scripts/verify_distribution.py
rbnx validate .
rbnx build -p .
```

For real inference, use Python 3.10 or 3.11 in a CUDA-compatible environment
and install `.[inference]`. The Wheel contains the Service adapter and the
OpenVLA/SpecVLA inference source; checkpoints remain deployment inputs and are
not stored in Git. Point `ROBONIX_SERVICE_PYTHON` at that environment when
RoboNix starts the Service. See [CAPABILITY.md](CAPABILITY.md) for the public
interface, [examples/minimal-deployment/README.md](examples/minimal-deployment/README.md)
for complete mock and real configurations, and [VALIDATION.md](VALIDATION.md)
for the exact validation boundary. The complete research implementation and
benchmark material below remain in this repository.

<a id="real-robonix-deployment"></a>
## Real RoboNix deployment

The release path is:

```text
Executor -> Atlas -> MCP -> vla_action_decision
         -> repository-packaged OpenVLA/SpecVLA source -> external checkpoints
```

It returns one candidate action and never commands robot hardware. Existing
checkpoints and observations should be connected from a large-volume data root
through checked symbolic links; do not copy weights into this repository. The
validation host's concrete storage layout and safe-link procedure are in
[benchmarks/target_server/README.md](benchmarks/target_server/README.md).

```bash
python3.10 -m venv /path/to/environments/vla-service
source /path/to/environments/vla-service/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,inference]'

rbnx validate .
rbnx build -p .

cd examples/real-deployment
cp .env.example .env
# Edit the untracked .env with checkpoint, input-root, GPU, cache, runtime,
# and Service-Python paths for this deployment.
set -a
source .env
set +a

rbnx build -f robonix_manifest.yaml
rbnx boot -v --no-update-check -f robonix_manifest.yaml
rbnx caps -v --server 127.0.0.1:50351
rbnx tools --server 127.0.0.1:50351
rbnx describe --server 127.0.0.1:50351 --provider vla_action_decision
rbnx inspect --server 127.0.0.1:50351
```

Before the first call, the Service process must not have mapped PyTorch and
must not occupy the selected GPU. Invoke through Executor:

```bash
python ../../benchmarks/target_server/invoke_executor.py \
  --atlas 127.0.0.1:50351 \
  --provider vla_action_decision \
  --contract robonix/service/vla/action_decision/decide \
  --args-json '{"instruction":"pick up the bowl","observation_uri":"/absolute/input/observation.jpg","timeout_s":600}' \
  --timeout-s 900

rbnx shutdown -f robonix_manifest.yaml
```

The first `decide` lazily imports the inference stack and loads both models.
If speculative decoding fails, the already-loaded target model is called; only
dual failure fails the MCP call. The local observation must remain below
`allowed_image_root` and pass signature, size, and pixel-count checks.
Configuration fields and defaults are defined in [config.spec](config.spec).

<a id="performance-snapshot"></a>
## 📊 Performance Snapshot

The motion-aware verification and recovery path improves end-to-end execution
speed while preserving task-level reliability across all four LIBERO suites.

| LIBERO suite | SR | Speedup |
| --- | ---: | ---: |
| Goal | 75.6% | 1.54× |
| Object | 72.3% | 1.49× |
| Spatial | **83.7%** | **1.57×** |
| Long | 48.8% | 1.48× |

## 📚 Table of Contents

- [Real RoboNix deployment](#real-robonix-deployment)
- [📊 Performance Snapshot](#performance-snapshot)
- [📰 News](#news)
- [⚡ System Capability and Results](#system-results)
- [🧠 Architecture Overview](#architecture)
- [🔌 RoboNix Integration and Outlook](#robonix-integration)
- [🧪 Validated Release](#validated-release)
- [⚙️ Requirements](#requirements)
- [🚀 Quick Start](#quick-start)
- [🧰 Installation and Configuration](#installation)
- [🏋️ Drafter Training](#training)
- [🎬 LIBERO Rollout](#rollout)
- [🗺️ Roadmap](#roadmap)
- [📝 Citation](#citation)
- [🤝 Contributors](#contributors)
- [📄 License](#license)

<a id="news"></a>
## 📰 News

- **2026-07-19**: 🆕 Released the system-level VLA action decision
  Service with capability results, model support, and bilingual documentation.
- **2026-07-18**: 🔥 Validated independent-root execution, target and Drafter
  checkpoint loading, and a bounded 100-step LIBERO rollout with H.264 video export.
- **2026-07-18**: 🛠️ Added configurable DeepSpeed paths, task selection, rollout
  step caps, and an import-compatible OpenVLA namespace.

<a id="system-results"></a>
## ⚡ System Capability and Results

From the RoboNix runtime perspective, this Service sits between candidate action
generation and robot execution. It verifies proposed actions, compensates
recoverable motion errors, and triggers deterministic policy fallback when a
candidate cannot be trusted.

| System-level result | Current capability |
| --- | --- |
| End-to-end acceleration | More than **1.45×** across evaluated LIBERO suites |
| Gain over fixed-threshold speculative execution | More than **25%** additional acceleration |
| Execution reliability | Near-baseline task success with motion-aware compensation and fallback |
| Open-source rollout | OpenVLA + trained Drafter, 100 bounded steps, H.264 video exported |

### Supported models

| Model family | Status | Scope |
| --- | --- | --- |
| OpenVLA | ✅ Completed | Drafter training, candidate generation, verification, compensation, fallback, and LIBERO rollout |
| Other token-based VLA models | ⏳ In progress | Pluggable model and Drafter interfaces are planned |

<a id="architecture"></a>
## 🧠 Architecture Overview

<!--
IMAGEGEN ASSET
Active asset: docs/assets/speculative-decoding-overview-v2.png
Regeneration prompt: docs/assets/IMAGEGEN_PROMPTS.md
The original SVG is retained as an editable fallback.
-->

<div align="center">
  <img width="96%" alt="RoboNix speculative decoding architecture" src="docs/assets/speculative-decoding-overview-v2.png" />
  <p><b>Figure 1.</b> Offline Drafter preparation and online speculative execution with confidence, kinematic acceptance, and target-policy fallback.</p>
</div>

Unlike fully autoregressive decoding, speculative decoding uses a smaller draft model to propose multiple candidates before invoking the target model. The target model validates these candidates in parallel. Actual speedup depends on the acceptance rate, candidate-tree shape, GPU, model configuration, and task, and must be measured against an autoregressive baseline under identical conditions.

<a id="robonix-integration"></a>
## 🔌 RoboNix Integration and Outlook

This Service is an independently deployable RoboNix provider connected through stable capability contracts. Physics-prior verification and fallback remain inside the provider, while Atlas handles discovery, Nexus transports requests, and Executor dispatches the resulting capability without changing the RoboNix core.

<div align="center">
  <img width="96%" alt="RoboNix system architecture" src="docs/assets/robonix-system-architecture.png" />
  <p><b>Figure 2.</b> System-level integration points for reusable memory services, custom services, and VLA-based user skills.</p>
</div>

Looking forward, the same interface can support additional Drafters, physical constraints, verification policies, and online data feedback. The long-term goal is a reusable embodied-execution service whose algorithms can evolve independently from robot hardware and the RoboNix runtime.

<a id="validated-release"></a>
## 🧪 Validated Release

Release candidate 0.1.0 was validated on 2026-08-01 with RoboNix commit
`48af09190b99f7847dddf68457eec2db42d2c1a7`, an A100 40GB GPU, the external
OpenVLA LIBERO-Goal checkpoint and compatible Drafter, and ten real
LIBERO-Goal observations.

| Route | Calls | Mean | P50 | P95 |
| --- | ---: | ---: | ---: | ---: |
| Direct target-only | 30 | 179.31 ms | 178.95 ms | 181.03 ms |
| Direct speculative | 30 | 176.12 ms | 173.00 ms | 202.72 ms |
| Executor -> Atlas -> MCP | 30 | 187.45 ms | 182.88 ms | 212.10 ms |

The 30 direct speculative and 30 full RoboNix actions matched exactly:
maximum error `0.0`. A real Drafter fault injection reached target-model
fallback, and shutdown returned GPU 1 from model occupancy to its 3 MiB idle
baseline. Model construction took 12.64 s; the first full Service call took
13.98 s; P50 wrapping overhead was 9.88 ms.

The measured target-to-speculative P50 speedup was only 1.034x, so this release
does not claim a material speedup. Process-level GPU allocation peaked at
39,603 MiB because the preserved TensorFlow preprocessing stack reserved most
remaining memory; this is an explicit deployment risk on a 40GB GPU.

![VLA action-decision latency](benchmarks/target_server/results/latency.svg)

Raw calls, fallback evidence, exact environment, and reporting limits are in
[benchmarks/target_server/](benchmarks/target_server/) and
[VALIDATION.md](VALIDATION.md).

Separately, the preserved research workflow previously completed a bounded
100-step LIBERO smoke rollout. It proves simulator integration and video
export, not task success:

![Validated 100-step LIBERO rollout](docs/assets/validated-rollout-preview.png)

*Validated smoke rollout: first, middle, and final frames from the 100-step run.*

<a id="quick-start"></a>
## 🚀 Quick Start

The repository never ships model weights or datasets. Point the commands below
to existing assets on a large data volume.

```bash
conda create -n robonix-spec python=3.10 -y
conda activate robonix-spec
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps

python -m pytest -q tests
python -m scripts.run --help
```

Run one bounded rollout with a compatible target checkpoint and Drafter:

```bash
export PYTHONPATH="$PWD/vendor/openvla:/path/to/LIBERO:${PYTHONPATH:-}"
export CUDA_VISIBLE_DEVICES=0
export MUJOCO_GL=egl
export MUJOCO_EGL_DEVICE_ID=0

python -m scripts.run \
  experiments/robot/libero/run_libero_goal_Spec.py \
  --model_family openvla \
  --pretrained_checkpoint /data/checkpoints/openvla_goal \
  --spec_checkpoint /data/checkpoints/drafter_goal \
  --task_suite_name libero_goal \
  --task_ids 0 \
  --num_trials_per_task 1 \
  --max_steps_override 100 \
  --local_log_dir /data/outputs/speculative \
  --center_crop True \
  --use_wandb False
```

Videos are written below `./rollouts/<date>/`; evaluation logs use the supplied
`--local_log_dir`. A 100-step cap is for deployment verification, not success
rate measurement.

<a id="requirements"></a>
## ⚙️ Requirements

| Component        | Requirement                                                                            |
| ---------------- | -------------------------------------------------------------------------------------- |
| Operating system | Linux recommended, especially for DeepSpeed and headless LIBERO/MuJoCo                 |
| Python           | 3.10+ for package checks; 3.10 or 3.11 for the pinned inference dependencies          |
| PyTorch          | 2.2.0                                                                                  |
| CUDA             | The upstream setup was tested with CUDA 12.1; match PyTorch, CUDA, and driver versions |
| Simulation       | LIBERO 0.1.0 and MuJoCo/EGL for evaluation                                             |
| Training         | DeepSpeed 0.16.6; multi-GPU hardware recommended                                       |

The repository does not include model weights, datasets, or LIBERO assets. Prepare the following before running the full pipeline:

- a target OpenVLA/VLA checkpoint;
- a compatible draft-model checkpoint for speculative evaluation;
- the LIBERO dataset and simulator environment;
- writable directories for generated data, checkpoints, and evaluation logs.

<a id="installation"></a>
## 🧰 Step 1: Installation

Clone the project and run all commands from the repository root:

```bash
git clone https://github.com/lusunn111/service-vla-action-decision-rbnx.git
cd service-vla-action-decision-rbnx

conda create -n spec-decoding python=3.10 -y
conda activate spec-decoding

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
```

The root `requirements.txt` is the reproducible installation entry and delegates
to `requirements/requirements-min.txt`. Additional LIBERO dependencies are in
`benchmarks/libero/experiments/libero_requirements.txt`. Install CUDA-dependent
packages using builds compatible with the local driver and toolkit.

Run lightweight smoke checks after installation:

```bash
python -c "import service_bootstrap as s; print(s.activate_vendor())"
python -m scripts.run --help
```

## 🔧 Step 2: Configuration

Copy the environment template and replace every placeholder with a local path:

```bash
cp configs/.env.example configs/.env
```

```dotenv
SPEC_MODEL_ROOT=/path/to/models
SPEC_DATA_ROOT=/path/to/datasets
SPEC_OUTPUT_ROOT=/path/to/outputs
LIBERO_ROOT=/path/to/libero
CUDA_VISIBLE_DEVICES=0
```

The template documents the path convention but is not loaded automatically by the current research scripts. Export the variables in the shell or pass the corresponding paths through each script's configuration.

Some preserved upstream scripts still contain machine-specific or `PATH_TO_*` placeholders. Locate and replace them before running a full experiment:

```bash
grep -R "PATH_TO\|/SpecVLA" scripts vendor/openvla/specdecoding \
  vendor/openvla/experiments/robot/libero
```

## 🧱 Step 3: Generate Draft-Model Training Data

The stable runner accepts a script path relative to `vendor/openvla/` and forwards all remaining arguments unchanged:

```bash
python -m scripts.run \
  specdecoding/train-scripts/ge_data_all_openvla_token_only_libero_goal.py \
  --start 0 \
  --end 100 \
  --index 0 \
  --gpu_index 0 \
  --outdir /path/to/generated-data
```

| Argument               | Description                                     |
| ---------------------- | ----------------------------------------------- |
| `--start`, `--end` | Range of samples to process                     |
| `--index`            | Worker or generation job index                  |
| `--gpu_index`        | One or more GPU indices                         |
| `--outdir`           | Output directory for generated training samples |

The script's `vla_path`, dataset path, and related values are currently source-level configuration fields. Set them to valid local assets before execution.

<a id="training"></a>
## 🏋️ Step 4: Train the Draft Model

1. Review `configs/ds_config.json` and `configs/llama_2_chat_7B_config.json`.
2. Configure the target VLA, generated dataset, and output paths in `FinetuneConfig`.
3. Launch training with DeepSpeed.

Example:

```bash
cd vendor/openvla/specdecoding/train-scripts

OPENVLA_CHECKPOINT=/path/to/openvla \
DRAFTER_TRAIN_DATA=/path/to/generated-data \
DRAFTER_OUTPUT_DIR=/path/to/drafter-checkpoints \
GPU_IDS=0,1 \
WANDB_MODE=offline \
bash train_ds_libero_goal.sh
```

Adjust GPU indices and the distributed port for the local environment. For reproducibility, record the Git revision, target-model version, data version, DeepSpeed configuration, GPU model, and random seed for every training run.

<a id="rollout"></a>
## 🎬 Step 5: Evaluate on LIBERO

Configure headless rendering before running an evaluation:

```bash
export CUDA_VISIBLE_DEVICES=0
export MUJOCO_GL=egl
export MUJOCO_EGL_DEVICE_ID=0
```

### Autoregressive Baseline

```bash
python -m scripts.run \
  experiments/robot/libero/run_libero_goal_AR.py \
  --model_family openvla \
  --pretrained_checkpoint /path/to/openvla-checkpoint \
  --task_suite_name libero_goal \
  --center_crop True \
  --use_wandb False
```

### Standard Speculative Decoding

```bash
python -m scripts.run \
  experiments/robot/libero/run_libero_goal_Spec.py \
  --model_family openvla \
  --pretrained_checkpoint /path/to/openvla-checkpoint \
  --spec_checkpoint /path/to/drafter-checkpoint \
  --task_suite_name libero_goal \
  --task_ids 0 \
  --num_trials_per_task 1 \
  --center_crop True \
  --use_wandb False
```

### Relaxed Acceptance

The repository retains experimental entry points for thresholds 9, 15, and 20. For example:

```bash
python -m scripts.run \
  experiments/robot/libero/run_libero_goal_Spec_Relaxed_15.py \
  --model_family openvla \
  --pretrained_checkpoint /path/to/openvla-checkpoint \
  --task_suite_name libero_goal \
  --center_crop True \
  --use_wandb False
```

Supported task suites include `libero_spatial`, `libero_object`, `libero_goal`, `libero_10`, and `libero_90`. Use `--center_crop True` when the target model was fine-tuned with the corresponding image augmentation. Supply a compatible Drafter with `--spec_checkpoint`; use `--task_ids` and `--max_steps_override` for bounded validation before running a complete suite.

## 📊 Benchmarking Guidelines

Run autoregressive and speculative entry points with the same hardware, target model, task suite, and random seeds. At minimum, report:

- task success rate and successful episode count;
- end-to-end episode latency;
- per-action generation latency and throughput;
- candidate acceptance rate and average accepted length;
- fallback count;
- peak GPU memory and utilization;
- candidate-tree width, depth, and acceptance configuration.

Do not report model-forward latency as end-to-end latency. Image preprocessing, simulator stepping, warm-up, synchronization, and logging can materially affect results. Warm up the model, repeat runs, and report both averages and percentiles.

## 🗂️ Repository Layout

```text
.
├── modules/                  # Lazy, task-oriented module catalogs
│   ├── drafter/              # Draft networks and proposal logic
│   ├── candidate_generation/ # Candidate-tree generation
│   ├── verification/         # Parallel target-model verification
│   ├── acceptance/           # Acceptance, KV cache, and fallback
│   ├── strategies/           # Standard and experimental strategies
│   ├── data/                 # Data-related entry points
│   └── training/             # Training-related entry points
├── scripts/                  # Stable runner and workflow entry points
├── benchmarks/libero/        # LIBERO experiments and speed tests
├── configs/                  # DeepSpeed, model, and environment templates
├── requirements.txt          # Reproducible installation entry
├── requirements/             # Core dependency pins
├── tests/                    # Layout, registry, and lazy-import tests
├── docs/assets/              # Architecture assets and the web ImageGen prompt
├── utils/                    # Common, loading, and KV-cache utilities
├── vendor/openvla/           # Canonical, import-compatible source tree
└── service_bootstrap.py      # Vendor activation and guarded script runner
```

`vendor/openvla/` is the canonical compatibility copy. The top-level `modules/`, `scripts/`, and `benchmarks/` directories provide an engineering-oriented view of the implementation. When changing an algorithm, clearly identify the authoritative layer and keep any convenience copies synchronized.

The default strategy is `modules.strategies.modeling_speculation`. The `_1`, `_14`, `_7d`, `_jiou`, and `_yuzhi` variants represent distinct research experiments and intentionally remain separate.

<a id="roadmap"></a>
## 🗺️ Roadmap

- [x] Publish an independently runnable source-only repository.
- [x] Validate target-model and Drafter loading plus bounded video rollout.
- [x] Package motion-aware verification, compensation, and policy fallback as one execution path.
- [x] Adopt the RoboNix Mulan PSL v2 license and remove citation placeholders.
- [ ] Publish compatible Drafter checkpoints with checksums and model cards.
- [ ] Add autoregressive-versus-speculative benchmark tables and acceptance metrics.
- [ ] Add more Drafter architectures and verification strategies.
- [ ] Validate additional VLA model families through the same Service contract.
- [x] Provide the versioned RoboNix Service adapter and capability contract.

<a id="citation"></a>
## 📝 Citation

If this Service supports your research, please consider giving the repository a
star ⭐ and citing this software repository:

```bibtex
@software{mao2026robonix_vla_action_decision_service,
  author  = {Mao, Zhihao and He, Huiru and Zheng, Zihao},
  title   = {RoboNix VLA Action Decision Service},
  year    = {2026},
  version = {0.1.0},
  url     = {https://github.com/lusunn111/service-vla-action-decision-rbnx}
}
```

<a id="contributors"></a>
## 🤝 Contributors

We thank [HuiruHe](https://github.com/HuiruHe) and
[zhengzihaoPKU](https://github.com/zhengzihaoPKU) for their contributions to
the Service. See [CONTRIBUTORS.md](CONTRIBUTORS.md) for the contributor policy.

<a id="license"></a>
## 📄 License

The project is licensed under the Mulan Permissive Software License, Version 2
(Mulan PSL v2); see [LICENSE](LICENSE). Vendored components retain their included
licenses.
