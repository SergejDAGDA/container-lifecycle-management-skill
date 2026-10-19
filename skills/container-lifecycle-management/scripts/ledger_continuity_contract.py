"""Experimental read-only witness-ledger continuity against an external anchor.

Reads an explicitly supplied filesystem-backed SQLite connection and verifies
its complete witness_used + witness_revoked state against an Ed25519 signed
statement AND an independently supplied *current* anchor ID. This module
never loads policy-selected files, signs data, writes to a journal, opens a
network/backup backend or authorizes production activity.

IMPORTANT: A signature alone DOES NOT prevent rollback. The expected
current anchor ID must come from a trusted, independently protected,
up-to-date authority, not this SQLite DB or the caller's untrusted document.
This code neither provides nor attests to such an authority.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from recovery_contract import HEX_SHA256, SNAPSHOT_ID
from witness_attestation_contract import SIGNATURE, WitnessTrustStore

SCHEMA = "witness-ledger-anchor/v1"
CLAIM = "LEDGER_STATE_OBSERVED"
ANCHOR_FIELDS = frozenset({
    "schema", "claim", "ledger_id", "witness_id", "key_id",
    "witness_fault_domain", "nonce", "state_digest", "used_count",
    "revoked_count", "revision", "issued_at_unix", "expires_at_unix",
})
TABLE_COLUMNS = {
    "witness_used": ("attestation_id", "witness_id", "key_id", "expires_at"),
    "witness_revoked": ("kind", "target"),
}
MAX_ROWS = 100_000


@dataclass(frozen=True)
class LedgerState:
    valid: bool
    digest: str | None
    used_count: int
    revoked_count: int
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class ContinuityDecision:
    status: str
    blockers: tuple[str, ...]
    anchor_id: str | None = None
    restore_authorized: bool = False
    off_host_proven: bool = False
    eligible_for_prune: bool = False


def _id(value: Any) -> bool:
    from witness_attestation_contract import _identifier
    return _identifier(value)


def _hex64(value: Any) -> bool:
    return isinstance(value, str) and bool(SNAPSHOT_ID.fullmatch(value))


def _hash(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX_SHA256.fullmatch(value))


def _encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def read_ledger_state(connection: Any) -> LedgerState:
    """Full bounded logical-state digest, never merely hash SQLite file bytes.

    A consistent read transaction includes both evidence tables. Invalid
    schemas, missing tables, active caller transactions, unsafe rows and
    inaccessible/corrupt files produce fixed diagnostic labels.
    """
    def blocked(code: str) -> LedgerState:
        return LedgerState(False, None, 0, 0, (code,))
    if not isinstance(connection, sqlite3.Connection):
        return blocked("continuity:invalid_connection")
    try:
        if connection.in_transaction:
            return blocked("continuity:active_transaction")
        dbs = connection.execute("PRAGMA database_list").fetchall()
        files = [record[2] for record in dbs if record[1] == "main"]
        if (len(files) != 1 or not files[0]
                or not Path(files[0]).is_file() or Path(files[0]).is_symlink()):
            return blocked("continuity:nonpersistent_ledger")
        connection.execute("BEGIN")
        if connection.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
            raise ValueError("continuity:corrupt_ledger")
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') "
            "AND name LIKE 'witness_%' LIMIT 1"
        ).fetchone():
            raise ValueError("continuity:unexpected_schema")
        sha = hashlib.sha256(b"msc-witness-ledger-state-v1\n")
        counts: dict[str, int] = {}
        for table, columns in TABLE_COLUMNS.items():
            spec = connection.execute("PRAGMA table_info(" + table + ")").fetchall()
            if (tuple(record[1] for record in spec) != columns
                    or any(record[2] != "TEXT" for record in spec if record[1] != "expires_at")
                    or (table == "witness_used" and spec[-1][2] != "INTEGER")):
                raise ValueError("continuity:unexpected_schema")
            order = "attestation_id" if table == "witness_used" else "kind,target"
            cursor = connection.execute(
                "SELECT " + ",".join(columns) + " FROM " + table + " ORDER BY " + order
            )
            sha.update(_encoded(["table", table]) + b"\n")
            count = 0
            for row in cursor:
                count += 1
                if count > MAX_ROWS:
                    raise ValueError("continuity:inventory_too_large")
                if table == "witness_used":
                    aid, witness, key, expiry = row
                    if (not _hex64(aid) or not _id(witness) or not _id(key)
                            or type(expiry) is not int or expiry < 0):
                        raise ValueError("continuity:invalid_ledger_row")
                else:
                    kind, target = row
                    if (kind not in ("attestation", "witness", "key")
                            or not isinstance(target, str)
                            or (kind == "attestation" and not _hex64(target))
                            or (kind == "witness" and not _id(target))
                            or (kind == "key" and (
                                len(target.split(":")) != 2
                                or any(not _id(part) for part in target.split(":"))))):
                        raise ValueError("continuity:invalid_ledger_row")
                sha.update(_encoded(list(row)) + b"\n")
            counts[table] = count
            sha.update(_encoded(["count", count]) + b"\n")
        connection.rollback()  # End read-only snapshot, do not modify state.
        return LedgerState(True, "sha256:" + sha.hexdigest(),
                           counts["witness_used"], counts["witness_revoked"], ())
    except (sqlite3.Error, ValueError, TypeError):
        try:
            if connection.in_transaction:
                connection.rollback()
        except sqlite3.Error:
            pass
        return blocked("continuity:unreadable_or_invalid_ledger")


def canonical_anchor(statement: Any) -> bytes:
    """Strict canonical anchor statement, suitable for external Ed25519 signers."""
    if not isinstance(statement, dict) or set(statement) != ANCHOR_FIELDS:
        raise ValueError("continuity:invalid_anchor_fields")
    if statement.get("schema") != SCHEMA or statement.get("claim") != CLAIM:
        raise ValueError("continuity:invalid_anchor_schema")
    if any(not _id(statement.get(name)) for name in
           ("ledger_id", "witness_id", "key_id", "witness_fault_domain")):
        raise ValueError("continuity:invalid_anchor_identity")
    if not _hex64(statement.get("nonce")) or not _hash(statement.get("state_digest")):
        raise ValueError("continuity:invalid_anchor_digest")
    for name in ("used_count", "revoked_count", "revision"):
        if type(statement.get(name)) is not int or not 0 <= statement[name] <= 2 * MAX_ROWS:
            raise ValueError("continuity:invalid_anchor_counters")
    if statement["revision"] != statement["used_count"] + statement["revoked_count"]:
        raise ValueError("continuity:invalid_anchor_revision")
    issued, expires = statement.get("issued_at_unix"), statement.get("expires_at_unix")
    if (type(issued) is not int or type(expires) is not int or issued < 0
            or not issued < expires <= issued + 3600):
        raise ValueError("continuity:invalid_anchor_clock")
    return _encoded(statement)


def verify_ledger_continuity(
    connection: Any, envelope: Any, trust: Any,
    *, ledger_id: Any, expected_current_anchor_id: Any, now_unix: Any,
) -> ContinuityDecision:
    """Match ledger to a signed, externally pinned current state.

    CRYPTO_MATCHED means only this logical SQLite state matches authenticated
    bytes and the caller-supplied anchor ID. It never proves the current ID
    itself was obtained from an independent/high-watermark authority.
    """
    def blocked(*codes: str) -> ContinuityDecision:
        return ContinuityDecision("BLOCKED", tuple(sorted(set(codes))))
    if (not isinstance(trust, WitnessTrustStore) or not _id(ledger_id)
            or not _hex64(expected_current_anchor_id)):
        return blocked("continuity:missing_independent_anchor_pin")
    if (not isinstance(envelope, dict) or set(envelope) != {"statement", "signature"}
            or not isinstance(envelope.get("signature"), str)
            or not SIGNATURE.fullmatch(envelope["signature"])):
        return blocked("continuity:invalid_envelope")
    try:
        signed = canonical_anchor(envelope["statement"])
    except ValueError:
        return blocked("continuity:invalid_anchor")
    statement = envelope["statement"]
    actual_anchor_id = hashlib.sha256(signed).hexdigest()
    if actual_anchor_id != expected_current_anchor_id:
        return blocked("continuity:not_latest_external_anchor")
    if statement["ledger_id"] != ledger_id:
        return blocked("continuity:ledger_identity_mismatch")
    if (type(now_unix) is not int
            or not statement["issued_at_unix"] <= now_unix <= statement["expires_at_unix"]):
        return blocked("continuity:stale_anchor")
    witness = trust.lookup(statement["witness_id"], statement["key_id"])
    if witness is None or witness.fault_domain != statement["witness_fault_domain"]:
        return blocked("continuity:unknown_anchor_signer")
    try:
        Ed25519PublicKey.from_public_bytes(witness.public_key).verify(
            bytes.fromhex(envelope["signature"]), signed,
        )
    except (ValueError, InvalidSignature):
        return blocked("continuity:invalid_signature")
    current = read_ledger_state(connection)
    if not current.valid:
        return blocked(*current.blockers)
    if (current.digest != statement["state_digest"]
            or current.used_count != statement["used_count"]
            or current.revoked_count != statement["revoked_count"]):
        return blocked("continuity:ledger_state_mismatch")
    return ContinuityDecision("CRYPTO_MATCHED", (), actual_anchor_id)
