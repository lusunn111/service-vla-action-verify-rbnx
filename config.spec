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
max_action_dim:
  type: integer
  default: 32
  constraint: greater than 0
