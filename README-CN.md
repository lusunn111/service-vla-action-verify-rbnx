<div align="center">

# RoboNix VLA 动作决策 Service

**面向具身模型的系统级动作决策、推测校验与目标模型回退 Service（服务）**

[English](README.md) · [🚀 快速开始](#quick-start) · [⚙️ 环境要求](#requirements) · [🧪 验证结果](#validated-release) · [📝 引用](#citation)

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-2.2-EE4C2C?logo=pytorch&logoColor=white)
![CUDA](https://img.shields.io/badge/CUDA-12.1-76B900?logo=nvidia&logoColor=white)
![LIBERO](https://img.shields.io/badge/LIBERO-rollout_verified-1f9d72)
[![License](https://img.shields.io/badge/license-MulanPSL--2.0-red)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/lusunn111/service-vla-action-decision-rbnx?style=flat&logo=github)](https://github.com/lusunn111/service-vla-action-decision-rbnx/stargazers)

</div>

**RoboNix VLA 动作决策 Service** 面向现有 VLA（视觉语言动作模型），让
低成本候选动作经过目标模型与运动先验共同校验后再进入执行。系统通过自适应接受、
运动补偿和策略回退减少重复的大模型推理，同时保持任务级执行可靠性。当前已支持
OpenVLA，以及 Drafter 候选生成、并行验证、运动感知补偿和原策略回退。

## RoboNix Service 软件包

仓库根目录可以直接作为 `robonix.service.vla.action_decision` 发布，对外提供
`robonix/service/vla/action_decision/decide`。Service 只返回候选动作，不控制
机器人硬件。RoboNix 激活阶段不会导入 PyTorch 或占用 GPU，目标模型与 Drafter
在第一次真实请求时延迟加载。

仓库检查使用：

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/release_audit.py
python -m build
python scripts/verify_distribution.py
rbnx validate .
rbnx build -p .
```

真实推理应使用 Python 3.10 或 3.11，并在匹配 CUDA 的环境中安装
`.[inference]`。Wheel（Python 二进制分发包）已经包含 Service 适配器和
OpenVLA/SpecVLA 推理源码，模型检查点仍作为部署输入，不进入 Git。RoboNix
启动时可用 `ROBONIX_SERVICE_PYTHON` 指向该推理环境。公开接口与安全边界见
[CAPABILITY.md](CAPABILITY.md)，完整模拟与真实配置见
[examples/minimal-deployment/README.md](examples/minimal-deployment/README.md)，
准确的验证边界见 [VALIDATION.md](VALIDATION.md)。下文的完整研究实现和基准材料
继续保留。

<a id="real-robonix-deployment"></a>
## 真实 RoboNix 部署

正式发布的真实数据流为：

```text
Executor（执行器）-> Atlas（能力注册中心）-> MCP（模型上下文协议）
-> vla_action_decision -> 仓库自带 OpenVLA/SpecVLA 推理源码 -> 外部检查点
```

该能力只返回一个候选动作，绝不直接控制机器人硬件。已有检查点和观测数据应从
独立大容量数据根目录通过核对后的软链接接入，不能把权重复制进仓库。测试机的具体
目录策略和安全链接命令见
[benchmarks/target_server/README.md](benchmarks/target_server/README.md)。

```bash
python3.10 -m venv /path/to/environments/vla-service
source /path/to/environments/vla-service/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,inference]'

rbnx validate .
rbnx build -p .

cd examples/real-deployment
cp .env.example .env
# 在不跟踪的 .env 中填写检查点、输入目录、GPU、缓存、运行目录和 Python 路径。
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

第一次调用前，Service 进程不应映射 PyTorch，也不应占用指定 GPU。真实调用必须
经过 Executor：

```bash
python ../../benchmarks/target_server/invoke_executor.py \
  --atlas 127.0.0.1:50351 \
  --provider vla_action_decision \
  --contract robonix/service/vla/action_decision/decide \
  --args-json '{"instruction":"pick up the bowl","observation_uri":"/absolute/input/observation.jpg","timeout_s":600}' \
  --timeout-s 900

rbnx shutdown -f robonix_manifest.yaml
```

第一次 `decide` 才导入推理依赖并加载两个模型。推测执行失败后会调用已加载的
目标模型，只有二者都失败才令 MCP 调用失败。观测图片必须位于
`allowed_image_root` 内，并通过签名、大小和像素数校验。全部配置字段和默认值
见 [config.spec](config.spec)。

<a id="performance-snapshot"></a>
## 📊 效果概览

运动感知校验与恢复链路在四个 LIBERO 套件上提升了端到端执行速度，同时保持
任务级执行可靠性。

| LIBERO 套件 | 成功率 | 加速比 |
| --- | ---: | ---: |
| Goal | 75.6% | 1.54× |
| Object | 72.3% | 1.49× |
| Spatial | **83.7%** | **1.57×** |
| Long | 48.8% | 1.48× |

## 📚 目录

- [真实 RoboNix 部署](#real-robonix-deployment)
- [📊 效果概览](#performance-snapshot)
- [📰 最新进展](#news)
- [⚡ 系统能力与效果](#system-results)
- [🧠 架构总览](#architecture)
- [🔌 RoboNix 集成与前景](#robonix-integration)
- [🧪 已验证版本](#validated-release)
- [⚙️ 环境要求](#requirements)
- [🚀 快速开始](#quick-start)
- [📦 检查点来源](#checkpoints)
- [🎬 LIBERO Rollout](#rollout)
- [🏋️ Drafter 训练](#training)
- [🗺️ 路线图](#roadmap)
- [📝 引用](#citation)
- [🤝 贡献者](#contributors)
- [📄 协议](#license)

<a id="news"></a>
## 📰 最新进展

- **2026-07-19**：🆕 发布系统级 VLA 动作决策 Service，补充能力效果、
  模型支持和中英文文档。
- **2026-07-18**：🔥 完成独立目录运行验证，成功加载目标模型与已有 Drafter，
  并导出 100 步 LIBERO H.264 rollout 视频。
- **2026-07-18**：🛠️ 开放 DeepSpeed 路径、任务选择和 rollout 步数上限配置。

<a id="system-results"></a>
## ⚡ 系统能力与效果

从 RoboNix 运行时视角看，该 Service 位于候选动作生成与机器人执行之间，负责校验
候选动作、补偿可恢复的运动误差，并在候选不可信时触发确定性的原策略回退。

| 系统级结果 | 当前能力 |
| --- | --- |
| 端到端加速 | 在已评测的 LIBERO 套件上达到 **1.45× 以上** |
| 相比固定阈值推测执行 | 获得 **25% 以上**的额外加速 |
| 执行可靠性 | 通过运动感知补偿和策略回退保持接近原策略的任务成功率 |
| 开源 rollout | OpenVLA + 已训练 Drafter，完成 100 步有界执行并导出 H.264 视频 |

### 支持模型

| 模型系列 | 状态 | 支持范围 |
| --- | --- | --- |
| OpenVLA | ✅ 已完成 | Drafter 训练、候选生成、校验、补偿、回退和 LIBERO rollout |
| 其他词元式 VLA | ⏳ 进行中 | 计划通过可插拔模型与 Drafter 接口接入 |

<a id="architecture"></a>
## 🧠 架构总览

<!--
IMAGEGEN ASSET
当前图片：docs/assets/speculative-decoding-overview-v2.png
重新生成提示词：docs/assets/IMAGEGEN_PROMPTS.md
原 SVG 继续作为可编辑备用文件保留。
-->

<div align="center">
  <img width="96%" alt="RoboNix 推测解码架构" src="docs/assets/speculative-decoding-overview-v2.png" />
  <p><b>图 1.</b> 离线 Drafter 准备，以及包含置信度、运动学接受和目标策略回退的在线推测执行链路。</p>
</div>

推测解码的系统收益不只取决于模型前向时间，还取决于候选接受率、候选树形状、
图像预处理、仿真执行、日志和回退开销。因此正式实验必须在相同硬件、模型和随机
种子下与自回归基线进行端到端比较。

<a id="robonix-integration"></a>
## 🔌 RoboNix 集成与前景

该 Service 是一个可独立部署的 RoboNix 能力提供方，通过稳定的能力契约接入系统。基于物理先验的验证与回退逻辑保留在能力提供方内部，Atlas 负责能力发现，Nexus 负责请求传输，Executor 负责能力调度，不需要修改 RoboNix 核心运行时。

<div align="center">
  <img width="96%" alt="RoboNix 系统架构" src="docs/assets/robonix-system-architecture.png" />
  <p><b>图 2.</b> 可复用记忆服务、自定义服务与基于 VLA 的用户技能在 RoboNix 中的系统级接入位置。</p>
</div>

未来可以在统一接口下继续扩展不同 Drafter、物理约束、验证策略和在线数据回流机制，使具身执行算法能够独立于机器人硬件和 RoboNix 核心持续演进。

<a id="validated-release"></a>
## 🧪 已验证版本

0.1.0 发布候选版本已于 2026-08-01 使用 RoboNix 提交
`48af09190b99f7847dddf68457eec2db42d2c1a7`、A100 40GB GPU、外部 OpenVLA
LIBERO-Goal 检查点、兼容 Drafter 和 10 个真实 LIBERO-Goal 观测完成验收。

| 路径 | 调用数 | 平均延迟 | P50 | P95 |
| --- | ---: | ---: | ---: | ---: |
| 直接目标模型 | 30 | 179.31 ms | 178.95 ms | 181.03 ms |
| 直接推测执行 | 30 | 176.12 ms | 173.00 ms | 202.72 ms |
| Executor -> Atlas -> MCP | 30 | 187.45 ms | 182.88 ms | 212.10 ms |

30 次直接推测执行和 30 次 RoboNix 全链路动作完全一致，最大误差为 `0.0`。
Drafter 真实故障注入成功进入目标模型回退；关闭后 GPU 1 从模型占用恢复到
3 MiB 空闲基线。模型构建耗时 12.64 秒，第一次完整 Service 调用耗时 13.98 秒，
P50 包装开销为 9.88 ms。

本次目标模型相对推测执行的 P50 加速比只有 1.034 倍，因此不能宣称显著性能收益。
由于保留的 TensorFlow 图像预处理栈会预留大部分剩余显存，进程级峰值达到
39,603 MiB；这对 40GB GPU 是必须明确披露的部署风险。

![VLA 动作决策延迟](benchmarks/target_server/results/latency.svg)

原始调用、回退证据、精确环境与报告边界见
[benchmarks/target_server/](benchmarks/target_server/) 和
[VALIDATION.md](VALIDATION.md)。

此外，仓库保留了此前研究链路完成的 100 步 LIBERO 有界冒烟测试。它证明仿真
接入和视频导出，不证明任务成功：

![已验证的 100 步 LIBERO rollout](docs/assets/validated-rollout-preview.png)

*100 步验证 rollout 的首帧、中间帧和末帧。*

<a id="quick-start"></a>
## 🚀 快速开始

仓库不包含模型、数据集或输出。建议把大文件放到独立数据盘，再通过绝对路径引用。

```bash
conda create -n robonix-spec python=3.10 -y
conda activate robonix-spec
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps

python -m pytest -q tests
python -m scripts.run --help
```

<a id="requirements"></a>
## ⚙️ 环境要求

| 组件 | 要求 |
| --- | --- |
| 操作系统 | 推荐 Linux，DeepSpeed 与无头 LIBERO/MuJoCo 评测依赖 Linux 环境 |
| Python | 软件包检查支持 3.10 以上；固定版本真实推理使用 3.10 或 3.11 |
| PyTorch | 2.2.0 |
| CUDA | 已验证环境为 CUDA 12.1，需与 PyTorch 和驱动版本匹配 |
| 仿真环境 | LIBERO 0.1.0、MuJoCo 与 EGL |
| 训练环境 | DeepSpeed 0.16.6，推荐多 GPU |

根目录 `requirements.txt` 是统一依赖入口，实际固定版本位于
`requirements/requirements-min.txt`。仓库不包含模型、数据集或运行输出。

<a id="checkpoints"></a>
## 📦 检查点从哪里来

| 资产 | 来源 |
| --- | --- |
| 目标 VLA | OpenVLA 官方仓库或 Hugging Face 上的 LIBERO 微调检查点 |
| Drafter | 使用本仓库的数据生成与 DeepSpeed 训练流程产生，或复用结构兼容的已有检查点 |
| LIBERO | 官方 LIBERO 源码、任务定义、初始状态和 MuJoCo/EGL 环境 |

目标 VLA 与 Drafter 必须在模型结构、词表、隐藏维度和动作编码上兼容。不要把任意
小模型检查点直接当作 Drafter 使用。

<a id="rollout"></a>
## 🎬 LIBERO Rollout

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

视频默认写入 `./rollouts/<日期>/`，日志写入 `--local_log_dir`。确认单任务、
单回合能够运行后，再移除任务和步数限制执行完整评测。

<a id="training"></a>
## 🏋️ Drafter 训练

先使用 `specdecoding/train-scripts/ge_data_all_openvla_token_only_libero_goal.py`
生成训练样本，再运行：

```bash
cd vendor/openvla/specdecoding/train-scripts

OPENVLA_CHECKPOINT=/data/checkpoints/openvla_goal \
DRAFTER_TRAIN_DATA=/data/drafter-training-data \
DRAFTER_OUTPUT_DIR=/data/checkpoints/drafter_goal \
GPU_IDS=0,1 \
WANDB_MODE=offline \
bash train_ds_libero_goal.sh
```

部署验收不需要跑完训练，可以直接加载已经训练好的兼容 Drafter 完成 rollout。

## 🗂️ 目录结构

```text
.
├── modules/                  # Drafter、候选、验证、接受和策略目录
├── scripts/                  # 稳定脚本入口
├── benchmarks/libero/        # LIBERO 评测与速度测试
├── configs/                  # DeepSpeed 与模型配置
├── requirements.txt          # 统一安装入口
├── requirements/             # 依赖固定版本
├── tests/                    # 结构与独立入口测试
├── vendor/openvla/           # 推测执行与 OpenVLA 兼容实现
├── docs/assets/              # 架构图和 rollout 预览
└── service_bootstrap.py      # 原始代码激活与安全脚本分发
```

`vendor/openvla/` 是论文行为的权威实现，`modules/` 与 `scripts/` 提供便于服务化
和后续接入 RoboNix 的工程视图。

<a id="roadmap"></a>
## 🗺️ 路线图

- [x] 发布可独立运行的纯源码仓库。
- [x] 验证目标模型、Drafter 加载和有界视频 rollout。
- [x] 将运动感知校验、补偿和策略回退整理为统一执行链路。
- [x] 采用与 RoboNix 一致的木兰宽松许可证并补全正式引用。
- [ ] 发布带校验值和模型卡的兼容 Drafter 检查点。
- [ ] 补充自回归与推测解码的端到端基准和接受率指标。
- [ ] 接入更多 Drafter 结构与验证策略。
- [ ] 通过统一 Service 契约验证更多 VLA 模型系列。
- [x] 提供带版本号的 RoboNix Service 适配器和能力契约。

<a id="citation"></a>
## 📝 引用

如果该 Service 对你的研究有帮助，欢迎给仓库一个 Star ⭐，并引用本软件仓库：

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
## 🤝 贡献者

感谢 [HuiruHe](https://github.com/HuiruHe) 和
[zhengzihaoPKU](https://github.com/zhengzihaoPKU) 对该 Service 的贡献。贡献者记录
规则见 [CONTRIBUTORS.md](CONTRIBUTORS.md)。

<a id="license"></a>
## 📄 协议

本项目采用木兰宽松许可证第 2 版(Mulan PSL v2)，详见 [LICENSE](LICENSE)；
第三方代码继续遵循各自目录中的原始协议。
