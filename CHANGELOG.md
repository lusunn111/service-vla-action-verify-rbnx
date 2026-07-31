# Changelog

## 0.1.0

- Publish the preserved speculative-decoding research tree as
  `robonix.service.vla.action_decision`.
- Add lazy in-process OpenVLA and Drafter loading with target-model fallback.
- Add a typed action contract, local-image boundary, lifecycle tests, package
  validation, and release automation.
- Add checkpoint-layout preflight, exact action-dimension validation, bounded
  instructions and timeouts, and configurable GPU visibility.
- Skip target fallback after deadline exhaustion and unload both models when
  speculative and target inference both fail.
- Package the actual OpenVLA and SpecVLA inference modules in the Wheel and
  source distribution instead of shipping an adapter without its runtime.
- Validate checkpoint statistics, decoded image size, typed booleans, and
  safe-boundary deadlines; preserve primary inference errors during cleanup.
- Add an isolated Wheel-install smoke test, explicit inference dependencies,
  guarded PID handling, selectable Service Python, and third-party notices.
