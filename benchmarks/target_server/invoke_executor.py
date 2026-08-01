#!/usr/bin/env python3
"""Invoke one published capability through Atlas and Executor."""

from __future__ import annotations

import argparse
import json

from executor_client import ExecutorClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atlas", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--args-json", required=True)
    parser.add_argument("--timeout-s", type=float, default=900.0)
    args = parser.parse_args()
    arguments = json.loads(args.args_json)
    if not isinstance(arguments, dict):
        raise SystemExit("--args-json must contain a JSON object")
    client = ExecutorClient(args.atlas, args.timeout_s)
    try:
        result = client.call(args.provider, args.contract, arguments)
    finally:
        client.close()
    print(json.dumps({"plan_id": result.plan_id, "elapsed_ms": result.elapsed_ms, "output": result.output}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
