"""Inference-focused Prismatic package included with the RoboNix Service.

The preserved research snapshot contains the Hugging Face inference modules
used by OpenVLA but not the upstream training-only ``prismatic.models`` tree.
Keeping this initializer side-effect free allows imports of
``openvla.prismatic.extern.hf`` in both a source checkout and an installed
Wheel.
"""

__all__: list[str] = []
