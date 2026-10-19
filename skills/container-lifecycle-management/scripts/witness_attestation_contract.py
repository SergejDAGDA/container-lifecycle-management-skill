"""Experimental signed independent-witness evidence, with a durable replay journal.

Uses externally pinned Ed25519 public keys to verify canonical statements.
A caller must independently authenticate witness identities, configure a
trusted clock and protect the SQLite journal. Neither a signature nor
successful recording proves remote infrastructure or authorizes restore,
deployment or pruning. No Docker, network, Restic or user service I/O.

The only persistent mutation is a narrowly scoped append-only SQLite replay
and revocation ledger, on a connection explicitly supplied by trusted code.
No API opens a policy-selected path or accepts a private signing key.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from recovery_contract import (
    HEX_SHA256, IDENTIFIER, SNAPSHOT_ID, validate_checkpoint, validate_recovery_set,
)
from storage_provider_contract import validate_storage_provider

SCHEMA = "independent-witness-attestation/v1"
SIGNATURE = re.compile(r"^[a-f0-9]{128}$")
STATEMENT_FIELDS = frozenset({
    "schema", "witness_id", "key_id", "witness_fault_domain",
    "nonce", "provider_fingerprint", "recovery_fingerprint",
    "snapshot_id", "compose_source_digest", "repository_id",
    "issued_at_unix", "expires_at_unix", "claim",
})
CLAIM = "INDEPENDENT_RESTORE_OBSERVED"


@dataclass(frozen=True)
class TrustedWitness:
    """Provisioned in reviewed code, not supplied by an attestation document."""

    witness_id: str
    key_id: str
    public_key: bytes
    fault_domain: str


@dataclass(frozen=True)
class WitnessDecision:
    status: str
    blockers: tuple[str, ...]
    attestation_id: str | None = None
    restore_authorized: bool = False
    off_host_proven: bool = False
    eligible_for_prune: bool = False


class WitnessTrustStore:
    def __init__(self, reviewed: tuple[TrustedWitness, ...]):
        if not isinstance(reviewed, tuple) or not reviewed:
            raise ValueError("witness:invalid_trust_registration")
        bindings = {}
        for witness in reviewed:
            if (not isinstance(witness, TrustedWitness)
                    or any(not _identifier(x) for x in
                           (witness.witness_id, witness.key_id, witness.fault_domain))
                    or type(witness.public_key) is not bytes
                    or len(witness.public_key) != 32
                    or (witness.witness_id, witness.key_id) in bindings):
                raise ValueError("witness:invalid_trust_registration")
            try:
                Ed25519PublicKey.from_public_bytes(witness.public_key)
            except ValueError as exc:
                raise ValueError("witness:invalid_trust_registration") from exc
            bindings[(witness.witness_id, witness.key_id)] = witness
        self._bindings = bindings

    def lookup(self, witness_id: Any, key_id: Any) -> TrustedWitness | None:
        if not _identifier(witness_id) or not _identifier(key_id):
            return None
        return self._bindings.get((witness_id, key_id))


def _identifier(value: Any) -> bool:
    return (isinstance(value, str)
            and ":" not in value
            and value.lower() not in {"unknown", "none", "missing", "unresolved"}
            and bool(IDENTIFIER.fullmatch(value)))


def _digest(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX_SHA256.fullmatch(value))


def canonical_statement(statement: Any) -> bytes:
    """Deterministic signed bytes. Reject extra fields and ambiguous input."""
    if not isinstance(statement, dict) or set(statement) != STATEMENT_FIELDS:
        raise ValueError("witness:invalid_statement_fields")
    if statement.get("schema") != SCHEMA or statement.get("claim") != CLAIM:
        raise ValueError("witness:unsupported_statement")
    if any(not _identifier(statement.get(k)) for k in
           ("witness_id", "key_id", "witness_fault_domain", "repository_id")):
        raise ValueError("witness:invalid_statement_identity")
    if (not isinstance(statement.get("nonce"), str)
            or not SNAPSHOT_ID.fullmatch(statement["nonce"])
            or not isinstance(statement.get("snapshot_id"), str)
            or not SNAPSHOT_ID.fullmatch(statement["snapshot_id"])
            or any(not _digest(statement.get(k)) for k in
                   ("provider_fingerprint", "recovery_fingerprint", "compose_source_digest"))):
        raise ValueError("witness:invalid_statement_scope")
    issued = statement.get("issued_at_unix")
    expires = statement.get("expires_at_unix")
    if (type(issued) is not int or type(expires) is not int
            or issued < 0 or expires <= issued or expires - issued > 3600):
        raise ValueError("witness:invalid_validity_window")
    try:
        return json.dumps(statement, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("witness:noncanonical_statement") from exc


class DurableWitnessLedger:
    """SQLite connection supplied by caller, never a policy-selected path.

    Persistent file and access-control durability are caller responsibilities.
    Atomic uniqueness works across processes using the *same* SQLite file.
    This does not make the file tamper-proof or survive lost storage.
    """

    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise ValueError("witness:invalid_ledger_connection")
        try:
            dbs = connection.execute("PRAGMA database_list").fetchall()
            files = [row[2] for row in dbs if row[1] == "main"]
            if (len(files) != 1 or not files[0]
                    or not Path(files[0]).is_file()
                    or Path(files[0]).is_symlink()
                    or connection.in_transaction):
                raise ValueError("witness:nonpersistent_ledger")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS witness_used ("
                "attestation_id TEXT PRIMARY KEY, witness_id TEXT NOT NULL, "
                "key_id TEXT NOT NULL, expires_at INTEGER NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS witness_revoked ("
                "kind TEXT NOT NULL, target TEXT NOT NULL, "
                "PRIMARY KEY(kind,target))"
            )
            connection.commit()
        except sqlite3.Error as exc:
            raise ValueError("witness:ledger_unavailable") from exc
        self._db = connection

    def _change(self, statement: dict, attestation_id: str) -> str:
        """Atomically test revocations and insert, never overwrite old IDs."""
        db = self._db
        try:
            db.execute("BEGIN IMMEDIATE")
            targets = (("attestation", attestation_id),
                       ("witness", statement["witness_id"]),
                       ("key", statement["witness_id"] + ":" + statement["key_id"]))
            for kind, target in targets:
                found = db.execute(
                    "SELECT 1 FROM witness_revoked WHERE kind=? AND target=?",
                    (kind, target),
                ).fetchone()
                if found:
                    db.rollback()
                    return "revoked"
            db.execute(
                "INSERT INTO witness_used (attestation_id,witness_id,key_id,expires_at) "
                "VALUES (?,?,?,?)",
                (attestation_id, statement["witness_id"], statement["key_id"],
                 statement["expires_at_unix"]),
            )
            db.commit()
            return "recorded"
        except sqlite3.IntegrityError:
            try:
                db.rollback()
            except sqlite3.Error:
                return "unavailable"
            return "replayed"
        except sqlite3.Error:
            try:
                db.rollback()
            except sqlite3.Error:
                pass
            return "unavailable"

    def revoke(self, kind: str, target: str) -> bool:
        """Append-only revocation of a signed ID, witness ID or key ID."""
        if (kind not in ("attestation", "witness", "key")
                or not isinstance(target, str)
                or (kind == "attestation" and not SNAPSHOT_ID.fullmatch(target))
                or (kind == "witness" and not _identifier(target))
                or (kind == "key" and
                    (len(target.split(":")) != 2 or
                     any(not _identifier(part) for part in target.split(":"))))):
            return False
        try:
            self._db.execute("BEGIN IMMEDIATE")
            self._db.execute(
                "INSERT OR IGNORE INTO witness_revoked(kind,target) VALUES (?,?)",
                (kind, target),
            )
            self._db.commit()
            return True
        except sqlite3.Error:
            self._db.rollback()
            return False

    def is_current(self, attestation_id: str, *, now_unix: int) -> bool:
        """Read-only current-record check, not verification or authorization."""
        if (not isinstance(attestation_id, str)
                or not SNAPSHOT_ID.fullmatch(attestation_id)
                or type(now_unix) is not int or now_unix < 0):
            return False
        try:
            record = self._db.execute(
                "SELECT witness_id,key_id,expires_at FROM witness_used "
                "WHERE attestation_id=?", (attestation_id,),
            ).fetchone()
            if not record or record[2] < now_unix:
                return False
            targets = (("attestation", attestation_id),
                       ("witness", record[0]),
                       ("key", record[0] + ":" + record[1]))
            return not any(self._db.execute(
                "SELECT 1 FROM witness_revoked WHERE kind=? AND target=?",
                (kind, target),
            ).fetchone() for kind, target in targets)
        except sqlite3.Error:
            return False


def verify_and_record(
    envelope: Any, trust: WitnessTrustStore, ledger: DurableWitnessLedger,
    recovery_set: Any, checkpoint: Any, provider: Any,
    *, now_unix: int,
) -> WitnessDecision:
    """Require a valid independent-domain signature and one-use durable ID.

    Cryptographic verification authenticates the configured key, NOT physical
    failure-domain separation or truthful witness claims. No status can grant
    automated mutation or attest complete production recovery.
    """
    blockers: list[str] = []
    if not isinstance(trust, WitnessTrustStore) or not isinstance(ledger, DurableWitnessLedger):
        return WitnessDecision("BLOCKED", ("witness:missing_trusted_context",))
    if (not isinstance(envelope, dict)
            or set(envelope) != {"statement", "signature"}
            or not isinstance(envelope.get("signature"), str)
            or not SIGNATURE.fullmatch(envelope["signature"])):
        return WitnessDecision("BLOCKED", ("witness:invalid_envelope",))
    statement = envelope["statement"]
    try:
        signed = canonical_statement(statement)
    except ValueError as exc:
        return WitnessDecision("BLOCKED", (str(exc),))
    if type(now_unix) is not int or not statement["issued_at_unix"] <= now_unix <= statement["expires_at_unix"]:
        blockers.append("witness:stale_or_future_statement")
    recovery = validate_recovery_set(recovery_set)
    provider_validation = validate_storage_provider(provider)
    fingerprint = recovery.fingerprint or ""
    checkpoint_validation = validate_checkpoint(checkpoint, recovery_fingerprint=fingerprint)
    if not recovery.valid or not provider_validation.valid:
        blockers.append("witness:invalid_recovery_or_provider")
    if not checkpoint_validation.valid or not checkpoint_validation.restore_tested:
        blockers.append("witness:missing_restore_test_proof")
    source = recovery_set.get("compose") if isinstance(recovery_set, dict) else None
    if (not isinstance(source, dict) or not isinstance(checkpoint, dict)
            or statement["recovery_fingerprint"] != fingerprint
            or statement["snapshot_id"] != checkpoint.get("id")
            or statement["compose_source_digest"] != source.get("source_digest")
            or statement["provider_fingerprint"] != provider_validation.fingerprint
            or not isinstance(provider, dict)
            or statement["repository_id"] != provider.get("repository_id")
            or checkpoint.get("provider") != provider.get("engine")):
        blockers.append("witness:scope_mismatch")
    witness = trust.lookup(statement["witness_id"], statement["key_id"])
    if witness is None:
        blockers.append("witness:unknown_or_revoked_trust_root")
    else:
        if statement["witness_fault_domain"] != witness.fault_domain:
            blockers.append("witness:untrusted_fault_domain")
        if (isinstance(provider, dict) and witness.fault_domain in (
                provider.get("source_fault_domain"),
                provider.get("repository_fault_domain"),
                provider.get("key_fault_domain"))):
            blockers.append("witness:not_independent_from_claimed_domains")
        try:
            Ed25519PublicKey.from_public_bytes(witness.public_key).verify(
                bytes.fromhex(envelope["signature"]), signed,
            )
        except (ValueError, InvalidSignature):
            blockers.append("witness:signature_invalid")
    if blockers:
        return WitnessDecision("BLOCKED", tuple(sorted(set(blockers))))
    attestation_id = hashlib.sha256(signed).hexdigest()
    result = ledger._change(statement, attestation_id)
    if result != "recorded":
        codes = {"revoked": "witness:revoked", "replayed": "witness:replayed",
                 "unavailable": "witness:ledger_unavailable"}
        return WitnessDecision("BLOCKED", (codes[result],))
    return WitnessDecision("CRYPTO_VERIFIED_RECORDED", (), attestation_id)
