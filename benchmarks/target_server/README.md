# Target-server benchmark

The benchmark has four explicit phases so the 15 GiB target model is never
loaded twice in one process:

1. `direct` measures target and speculative inference from this repository.
2. `service` measures the complete Executor -> Atlas -> MCP -> Service route.
3. `fallback` injects a Drafter exception in the benchmark harness after real
   model loading and verifies target-model fallback.
4. `summary` checks direct/Service action parity and writes structured results.

Example:

```bash
python run_benchmark.py direct --input-root /absolute/inputs \
  --target-checkpoint /absolute/openvla --drafter-checkpoint /absolute/drafter \
  --output-dir results
# Boot the real RoboNix deployment before the service phase.
python run_benchmark.py service --input-root /absolute/inputs \
  --target-checkpoint /absolute/openvla --drafter-checkpoint /absolute/drafter \
  --output-dir results
python run_benchmark.py fallback --input-root /absolute/inputs \
  --target-checkpoint /absolute/openvla --drafter-checkpoint /absolute/drafter \
  --output-dir results
python run_benchmark.py summary --output-dir results
python render_results.py
```

This is a Service performance and parity benchmark, not a full LIBERO success-
rate evaluation. Commit only structured results, hashes, and sanitized metadata.
