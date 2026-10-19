#!/usr/bin/env python3
"""Dependency preflight for the read-only maintenance helper.

Python standard library only. Does not install anything, contact Docker,
read the policy file or disclose environment variables or credentials.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def check_dependencies() -> dict:
    supported_python = sys.version_info >= (3, 10)
    try:
        yaml_present = importlib.util.find_spec("yaml") is not None
    except (ValueError, ImportError):
        yaml_present = False
    return {
        "python_compatible": supported_python,
        "pyyaml_available": yaml_present,
        "yaml_policy_ready": supported_python and yaml_present,
        "json_policy_ready": supported_python,
        "read_only": True,
        "dependencies_modified": False,
        "note": (
            "For YAML, run maintenance.py with an existing Python environment "
            "that already has PyYAML. If unavailable, create a separate local "
            "venv outside the server (with permission) and install the declared "
            "requirements there. Never silently install packages on the "
            "inspected server. JSON policy validation needs no PyYAML."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline read-only validator dependency check")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    status = check_dependencies()
    if args.format == "json":
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print("Python >=3.10: " + ("PASS" if status["python_compatible"] else "BLOCKED"))
        print("PyYAML for YAML policies: " + ("PASS" if status["pyyaml_available"] else "MISSING"))
        print(status["note"])
    return 0 if status["yaml_policy_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
