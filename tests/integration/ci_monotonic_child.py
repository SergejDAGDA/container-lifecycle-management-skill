"""Single-use CI-only cross-process CAS on a fixture-owned SQLite path.

No network, Docker, shell, real paths or policy-selected provider. This worker
exits after exactly one fixed-shape request against a recognized disposable
CI namespace. It must not be installed or used for real anchor publication.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "skills" / "container-lifecycle-management" / "scripts"))
from monotonic_head_contract import SyntheticMonotonicJournal  # noqa: E402

FIELDS = {
    "path", "ledger_id", "store_id", "genesis", "expected_revision",
    "expected_anchor", "next_revision", "next_anchor", "minimum_revision",
}
HEX = re.compile(r"^[a-f0-9]{64}$")
LEDGER = re.compile(r"^[a-zA-Z0-9_.-]{1,96}$")


def main() -> int:
    if os.environ.get("MSC_DISPOSABLE_TEST_RUNNER") != "isolated-ci-fixture-v1":
        return 10
    wire = sys.stdin.buffer.read(4097)
    if len(wire) > 4096:
        return 11
    try:
        obj = json.loads(wire)
        if not isinstance(obj, dict) or set(obj) != FIELDS:
            return 12
        raw_path = obj["path"]
        if not isinstance(raw_path, str):
            return 13
        path = Path(raw_path)
        if (not path.is_absolute() or path.is_symlink()
                or path.name != "ci-monotonic-heads.sqlite"
                or not path.parent.name.startswith("msc-pg-disposable-")
                or not path.is_file()):
            return 14
        if (not LEDGER.fullmatch(obj["ledger_id"])
                or any(not isinstance(obj[k], str) or not HEX.fullmatch(obj[k])
                       for k in ("store_id", "genesis", "expected_anchor", "next_anchor"))
                or any(type(obj[k]) is not int or not 0 <= obj[k] <= 200_000
                       for k in ("expected_revision", "next_revision", "minimum_revision"))):
            return 15
        with sqlite3.connect(path, timeout=8) as db:
            journal = SyntheticMonotonicJournal(
                db, ledger_id=obj["ledger_id"],
                expected_store_id=obj["store_id"],
                expected_genesis_anchor=obj["genesis"],
            )
            outcome = journal.compare_and_swap(
                expected_revision=obj["expected_revision"],
                expected_anchor_id=obj["expected_anchor"],
                new_revision=obj["next_revision"],
                new_anchor_id=obj["next_anchor"],
                trusted_min_revision=obj["minimum_revision"],
            )
        print(json.dumps({"status": outcome.status, "blockers": outcome.blockers},
                         separators=(",", ":")))
        return 0
    except (KeyError, TypeError, ValueError, sqlite3.Error, OSError):
        return 16


if __name__ == "__main__":
    raise SystemExit(main())
