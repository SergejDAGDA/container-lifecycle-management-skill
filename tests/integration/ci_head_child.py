"""One-shot, disposable synthetic signing child over stdin/stdout.

Only called by tests/integration/ci_forked_head.py using a fixed file path.
Never reads real keys, storage, service settings or a network connection.
The seed arriving on stdin is synthetic and deliberately NOT safely escrowed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills" / "container-lifecycle-management" / "scripts"))
from current_anchor_source_contract import CLAIM, SCHEMA, canonical_head  # noqa: E402

FIELDS = frozenset({
    "schema", "ledger_id", "challenge", "anchor_id", "revision",
    "now_unix", "synthetic_seed_hex", "mode", "replay_reply",
})
MODES = {"normal", "crash", "drop", "silence", "foreign_key", "old_revision",
         "replay", "wrong_anchor"}


def main() -> int:
    data = sys.stdin.buffer.read(8193)
    if len(data) > 8192:
        return 3
    try:
        request = json.loads(data)
        if (not isinstance(request, dict) or set(request) != FIELDS
                or request.get("schema") != "ci-anchor-worker/v1"
                or request.get("mode") not in MODES
                or type(request.get("now_unix")) is not int
                or type(request.get("revision")) is not int
                or not isinstance(request.get("synthetic_seed_hex"), str)
                or len(request["synthetic_seed_hex"]) != 64):
            return 4
        signing_seed = bytes.fromhex(request["synthetic_seed_hex"])
        signer = Ed25519PrivateKey.from_private_bytes(signing_seed)
        if request["mode"] == "crash":
            os._exit(17)
        if request["mode"] == "silence":
            time.sleep(6)
            return 18
        if request["mode"] == "drop":
            sys.stdout.write('{"message":')
            return 0
        if request["mode"] == "replay":
            if not isinstance(request["replay_reply"], dict):
                return 5
            sys.stdout.write(json.dumps(request["replay_reply"], separators=(",", ":")))
            return 0
        if request["mode"] == "foreign_key":
            signer = Ed25519PrivateKey.from_private_bytes(
                hashlib.sha256(b"ci-different-key-only").digest())
        now = request["now_unix"]
        statement = {
            "schema": SCHEMA, "claim": CLAIM,
            "source_id": "ci-process-head", "key_id": "ci-process-key",
            "ledger_id": request["ledger_id"],
            "challenge": request["challenge"],
            "anchor_id": ("e" * 64 if request["mode"] == "wrong_anchor"
                          else request["anchor_id"]),
            "revision": request["revision"] - (1 if request["mode"] == "old_revision" else 0),
            "issued_at_unix": now,
            "expires_at_unix": now + 30,
        }
        payload = canonical_head(statement)
        reply = {"message": statement, "signature": signer.sign(payload).hex()}
        sys.stdout.write(json.dumps(reply, separators=(",", ":")))
        return 0
    except (ValueError, TypeError, KeyError, OverflowError):
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
