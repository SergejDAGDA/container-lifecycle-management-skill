"""Experimental code-registered source for a signed current ledger anchor.

Pure verification/orchestration. Calls one explicitly registered inspector
object supplied by reviewed code. Never imports adapters selected by policy,
opens network destinations, reads secrets or grants a restore/delete action.

Authenticating the source's key and fresh challenge does NOT prove the source
is remotely operated, monotonic, independently protected or truthful.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ledger_continuity_contract import (
    _id, _hex64, canonical_anchor, verify_ledger_continuity,
)
from witness_attestation_contract import SIGNATURE, WitnessTrustStore

SCHEMA = "current-anchor-head-response/v1"
CLAIM = "CURRENT_ANCHOR_HEAD"
FIELDS = frozenset({
    "schema", "claim", "source_id", "key_id", "ledger_id", "challenge",
    "anchor_id", "revision", "issued_at_unix", "expires_at_unix",
})


@dataclass(frozen=True)
class ReviewedHeadSource:
    source_id: str
    key_id: str
    fault_domain: str
    public_key: bytes
    source_file_sha256: str
    source: object


@dataclass(frozen=True)
class AnchorHeadDecision:
    status: str
    blockers: tuple[str, ...]
    anchor_id: str | None = None
    restore_authorized: bool = False
    off_host_proven: bool = False
    eligible_for_prune: bool = False


def _blocked(code: str) -> AnchorHeadDecision:
    return AnchorHeadDecision("BLOCKED", (code,))


def canonical_head(message: Any) -> bytes:
    """Reject unknown fields, wrong types and non-canonical response identity."""
    if not isinstance(message, dict) or set(message) != FIELDS:
        raise ValueError("head:invalid_response_fields")
    if message.get("schema") != SCHEMA or message.get("claim") != CLAIM:
        raise ValueError("head:invalid_response_schema")
    if any(not _id(message.get(k)) for k in ("source_id", "key_id", "ledger_id")):
        raise ValueError("head:invalid_response_identity")
    if not _hex64(message.get("challenge")) or not _hex64(message.get("anchor_id")):
        raise ValueError("head:invalid_response_scope")
    if type(message.get("revision")) is not int or not 0 <= message["revision"] <= 200_000:
        raise ValueError("head:invalid_response_revision")
    start, end = message.get("issued_at_unix"), message.get("expires_at_unix")
    if (type(start) is not int or type(end) is not int
            or start < 0 or not start < end <= start + 120):
        raise ValueError("head:invalid_response_clock")
    return json.dumps(message, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


class ReviewedHeadReader:
    """Bind one source object and public key in code, without policy imports."""

    def __init__(self, reviewed_root: Path, binding: ReviewedHeadSource):
        if (not isinstance(reviewed_root, Path) or reviewed_root.is_symlink()
                or not reviewed_root.is_dir() or not isinstance(binding, ReviewedHeadSource)
                or any(not _id(x) for x in
                       (binding.source_id, binding.key_id, binding.fault_domain))
                or type(binding.public_key) is not bytes or len(binding.public_key) != 32
                or not isinstance(binding.source_file_sha256, str)
                or not binding.source_file_sha256.startswith("sha256:")
                or len(binding.source_file_sha256) != 71):
            raise ValueError("head:invalid_reviewed_registration")
        try:
            Ed25519PublicKey.from_public_bytes(binding.public_key)
        except ValueError as exc:
            raise ValueError("head:invalid_reviewed_registration") from exc
        self._root = reviewed_root.resolve()
        self._binding = binding
        self._check_source()

    def _check_source(self) -> None:
        try:
            path = Path(inspect.getfile(type(self._binding.source)))
            if path.is_symlink() or not path.is_file():
                raise ValueError("head:unreviewed_source")
            actual = path.resolve(strict=True)
            if not actual.is_relative_to(self._root):
                raise ValueError("head:unreviewed_source")
            if ("sha256:" + hashlib.sha256(actual.read_bytes()).hexdigest()
                    != self._binding.source_file_sha256):
                raise ValueError("head:source_pin_mismatch")
        except (OSError, TypeError) as exc:
            raise ValueError("head:unreviewed_source") from exc

    def evaluate(
        self, connection: Any, anchor_envelope: Any, anchor_trust: Any,
        *, ledger_id: Any, now_unix: Any, trusted_min_revision: Any,
        max_age_seconds: int = 30,
    ) -> AnchorHeadDecision:
        """Request a fresh head and combine it with ledger continuity.

        All successful comparisons remain non-authorizing source claims.
        trusted_min_revision must be provided by a trusted caller. A locally
        derived minimum cannot guarantee anti-rollback.
        """
        binding = self._binding
        if (not _id(ledger_id) or type(now_unix) is not int or now_unix < 0
                or type(trusted_min_revision) is not int or not 0 <= trusted_min_revision <= 200_000
                or type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 120):
            return _blocked("head:untrusted_clock_or_minimum")
        if not isinstance(anchor_trust, WitnessTrustStore):
            return _blocked("head:missing_anchor_trust")
        try:
            signed_anchor = canonical_anchor(anchor_envelope["statement"])
            anchor = anchor_envelope["statement"]
            if (set(anchor_envelope) != {"statement", "signature"}
                    or not isinstance(anchor_envelope["signature"], str)
                    or not SIGNATURE.fullmatch(anchor_envelope["signature"])):
                return _blocked("head:invalid_anchor_envelope")
        except (KeyError, TypeError, ValueError):
            return _blocked("head:invalid_anchor_envelope")
        if anchor["ledger_id"] != ledger_id:
            return _blocked("head:ledger_identity_mismatch")
        anchor_witness = anchor_trust.lookup(anchor["witness_id"], anchor["key_id"])
        if (anchor_witness is None
                or anchor_witness.fault_domain == binding.fault_domain):
            return _blocked("head:untrusted_or_shared_signer_domain")
        try:
            self._check_source()
        except ValueError:
            return _blocked("head:source_pin_invalid")

        # New unpredictable challenge per evaluation. No replay state or network.
        challenge = secrets.token_hex(32)
        try:
            reply = binding.source.read_current_head(ledger_id, challenge)
        except Exception:
            return _blocked("head:source_unavailable")
        if (not isinstance(reply, dict) or set(reply) != {"message", "signature"}
                or not isinstance(reply.get("signature"), str)
                or not SIGNATURE.fullmatch(reply["signature"])):
            return _blocked("head:invalid_signed_reply")
        try:
            wire = canonical_head(reply["message"])
        except ValueError:
            return _blocked("head:invalid_signed_reply")
        message = reply["message"]
        if (message["source_id"] != binding.source_id or message["key_id"] != binding.key_id
                or message["ledger_id"] != ledger_id):
            return _blocked("head:unexpected_source_identity")
        if message["challenge"] != challenge:
            return _blocked("head:challenge_mismatch")
        if (message["issued_at_unix"] > now_unix
                or message["expires_at_unix"] < now_unix
                or now_unix - message["issued_at_unix"] > max_age_seconds):
            return _blocked("head:stale_or_future_source_reply")
        try:
            Ed25519PublicKey.from_public_bytes(binding.public_key).verify(
                bytes.fromhex(reply["signature"]), wire)
        except (ValueError, InvalidSignature):
            return _blocked("head:invalid_source_signature")
        if message["revision"] < trusted_min_revision:
            return _blocked("head:below_trusted_minimum")
        if (message["anchor_id"] != hashlib.sha256(signed_anchor).hexdigest()
                or message["revision"] != anchor["revision"]):
            return _blocked("head:source_head_mismatch")
        continuity = verify_ledger_continuity(
            connection, anchor_envelope, anchor_trust, ledger_id=ledger_id,
            expected_current_anchor_id=message["anchor_id"], now_unix=now_unix)
        if continuity.status != "CRYPTO_MATCHED":
            return AnchorHeadDecision("BLOCKED", continuity.blockers)
        return AnchorHeadDecision("SIGNED_SOURCE_CLAIM_MATCHED", (), message["anchor_id"])
