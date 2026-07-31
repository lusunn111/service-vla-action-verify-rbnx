# Public deployment configuration for robonix.service.vla.action_decision.
backend_mode:
  type: enum[openvla,mock]
  default: openvla
  description: Load the preserved OpenVLA plus Drafter implementation or use a non-executable lifecycle test backend.
target_checkpoint:
  type: absolute_path
  required_when: backend_mode=openvla
drafter_checkpoint:
  type: absolute_path
  required_when: backend_mode=openvla
allowed_image_root:
  type: absolute_path
  required_when: backend_mode=openvla
  description: Only local observation images below this directory may be read.
cuda_visible_devices:
  type: string
  default: ""
  description: Optional comma-separated physical GPU indices applied before PyTorch is imported. Logical cuda:0 maps to the first index.
require_cuda:
  type: boolean
  default: true
  description: Reject real inference when CUDA is unavailable instead of accidentally loading the 15GB target model on CPU.
unnorm_key:
  type: string
  default: libero_goal
center_crop:
  type: boolean
  default: true
accept_threshold:
  type: integer
  default: 9
parallel_draft:
  type: boolean
  default: false
load_in_8bit:
  type: boolean
  default: false
load_in_4bit:
  type: boolean
  default: false
max_image_bytes:
  type: integer
  default: 10485760
  constraint: greater than 0
max_image_pixels:
  type: integer
  default: 16777216
  constraint: greater than 0
  description: Maximum decoded observation pixel count accepted by the model adapter.
max_action_dim:
  type: integer
  default: 32
  constraint: greater than 0
expected_action_dim:
  type: integer
  default: 7
  constraint: greater than 0
  description: Exact action dimension required from both speculative and target inference.
max_instruction_chars:
  type: integer
  default: 4096
  constraint: greater than 0
max_timeout_s:
  type: float
  default: 300.0
  constraint: greater than 0
  description: Upper bound accepted for request timeout_s. GPU inference is non-preemptible and is checked at safe boundaries.
