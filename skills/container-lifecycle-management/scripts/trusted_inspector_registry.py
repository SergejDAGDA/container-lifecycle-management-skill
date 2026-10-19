"""Code-registered read-only storage inspectors and single-use observations.

EXPERIMENTAL, no production adapter registration, Docker, network, backup,
restore, policy-selected imports or permission to prune. The registry accepts
inspector objects only from *reviewed calling code*, not policy files. A
runtime source-file SHA-256 check and one-use challenge guard accidental
replacement and stale reuse. These do not authenticate a remote provider,
process compromise, or fabricated inspector observations.
"""
from __future__ import annotations

import hashlib
import inspect
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from recovery_contract import HEX_SHA256, IDENTIFIER, validate_checkpoint, validate_recovery_set
from storage_provider_contract import assess_storage_evidence, validate_storage_provider


class RegistryRefusal(RuntimeError):
    """Fixed diagnostic, never include path, exception detail or credentials."""


@dataclass(frozen=True)
class ReviewedInspector:
    """Review-time binding supplied as an object by code, never configuration."""

    provider_id: str
    issuer_id: str
    provider_fingerprint: str
    source_digest: str
    inspector: object


@dataclass(frozen=True)
class ObservationTicket:
    """Identity-scoped, in-process one-use attempt; not a signed attestation."""

    nonce: str
    provider_id: str
    provider_fingerprint: str
    recovery_fingerprint: str
    snapshot_id: str
    compose_digest: str
    issued_at_unix: int


@dataclass(frozen=True)
class RegisteredEvidenceResult:
    status: str
    blockers: tuple[str, ...]
    restore_authorized: bool = False
    off_host_proven: bool = False
    eligible_for_prune: bool = False


class ReviewedInspectorRegistry:
    """Code-only registry. A policy may describe a provider, never register one."""

    def __init__(self, trusted_root: Path, bindings: tuple[ReviewedInspector, ...]):
        if not isinstance(trusted_root, Path) or not trusted_root.is_dir() or trusted_root.is_symlink():
            raise RegistryRefusal("registry:invalid_trusted_root")
        self._root = trusted_root.resolve()
        if not isinstance(bindings, tuple) or not bindings:
            raise RegistryRefusal("registry:empty_or_invalid_bindings")
        registered: dict[str, ReviewedInspector] = {}
        for entry in bindings:
            if (not isinstance(entry, ReviewedInspector)
                    or not isinstance(entry.provider_id, str)
                    or not isinstance(entry.issuer_id, str)
                    or not isinstance(entry.provider_fingerprint, str)
                    or not isinstance(entry.source_digest, str)
                    or not bool(HEX_SHA256.fullmatch(entry.provider_fingerprint))
                    or not bool(HEX_SHA256.fullmatch(entry.source_digest))
                    or not bool(IDENTIFIER.fullmatch(entry.provider_id))
                    or not bool(IDENTIFIER.fullmatch(entry.issuer_id))
                    or entry.provider_id in registered):
                raise RegistryRefusal("registry:invalid_or_duplicate_binding")
            self._source_check(entry)
            registered[entry.provider_id] = entry
        self._registered = registered
        self._pending: dict[str, ObservationTicket] = {}

    def _source_check(self, entry: ReviewedInspector) -> None:
        try:
            source = Path(inspect.getfile(type(entry.inspector)))
            if source.is_symlink() or not source.is_file():
                raise RegistryRefusal("registry:untrusted_inspector_source")
            actual = source.resolve(strict=True)
            if not actual.is_relative_to(self._root):
                raise RegistryRefusal("registry:inspector_outside_reviewed_root")
            if "sha256:" + hashlib.sha256(actual.read_bytes()).hexdigest() != entry.source_digest:
                raise RegistryRefusal("registry:inspector_source_pin_mismatch")
        except (OSError, TypeError, ValueError) as exc:
            raise RegistryRefusal("registry:untrusted_inspector_source") from exc

    def issue(
        self, provider: Any, recovery_set: Any, checkpoint: Any,
        *, now_unix: int,
    ) -> ObservationTicket:
        """Bind one attempt to an exact code-registered provider and checkpoint."""
        if type(now_unix) is not int or now_unix < 0:
            raise RegistryRefusal("registry:invalid_clock")
        descriptor = validate_storage_provider(provider)
        recovery = validate_recovery_set(recovery_set)
        if (not descriptor.valid or not recovery.valid
                or not descriptor.fingerprint or not recovery.fingerprint):
            raise RegistryRefusal("registry:invalid_declaration")
        entry = self._registered.get(provider["provider_id"])
        if entry is None:
            raise RegistryRefusal("registry:adapter_not_registered")
        if (entry.provider_fingerprint != descriptor.fingerprint
                or entry.source_digest != provider["adapter_source_digest"]):
            raise RegistryRefusal("registry:adapter_pin_mismatch")
        checked = validate_checkpoint(checkpoint, recovery_fingerprint=recovery.fingerprint)
        if not checked.valid or not checked.restore_tested:
            raise RegistryRefusal("registry:checkpoint_not_restore_tested")
        self._source_check(entry)
        ticket = ObservationTicket(
            nonce=secrets.token_hex(16), provider_id=entry.provider_id,
            provider_fingerprint=descriptor.fingerprint,
            recovery_fingerprint=recovery.fingerprint,
            snapshot_id=checkpoint["id"],
            compose_digest=recovery_set["compose"]["source_digest"],
            issued_at_unix=now_unix,
        )
        self._pending[ticket.nonce] = ticket
        return ticket

    def observe(
        self, ticket: ObservationTicket, provider: Any,
        recovery_set: Any, checkpoint: Any,
        *, now_unix: int, max_age_seconds: int = 300,
        require_off_host: bool = True,
    ) -> RegisteredEvidenceResult:
        """Call only the registered inspector instance, at most once.

        Consume attempts on *every* outcome. Checked identities and timestamps
        are still local claims. All outcomes are non-authorizing.
        """
        if not isinstance(ticket, ObservationTicket):
            return RegisteredEvidenceResult("BLOCKED", ("registry:invalid_ticket",))
        recorded = self._pending.pop(ticket.nonce, None)
        if recorded is not ticket:
            return RegisteredEvidenceResult("BLOCKED", ("registry:replayed_or_forged_ticket",))
        entry = self._registered.get(ticket.provider_id)
        if entry is None:
            return RegisteredEvidenceResult("BLOCKED", ("registry:adapter_not_registered",))
        if (type(now_unix) is not int or now_unix < ticket.issued_at_unix
                or type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 3600
                or now_unix - ticket.issued_at_unix > max_age_seconds):
            return RegisteredEvidenceResult("BLOCKED", ("registry:expired_attempt",))
        try:
            descriptor = validate_storage_provider(provider)
            recovery = validate_recovery_set(recovery_set)
            if (not descriptor.valid or descriptor.fingerprint != ticket.provider_fingerprint
                    or not recovery.valid or recovery.fingerprint != ticket.recovery_fingerprint
                    or not isinstance(checkpoint, dict)
                    or checkpoint.get("id") != ticket.snapshot_id
                    or checkpoint.get("recovery_fingerprint") != ticket.recovery_fingerprint
                    or not isinstance(provider, dict)
                    or provider.get("provider_id") != ticket.provider_id
                    or provider.get("adapter_source_digest") != entry.source_digest
                    or not isinstance(recovery_set, dict)
                    or recovery_set.get("compose", {}).get("source_digest") != ticket.compose_digest):
                return RegisteredEvidenceResult("BLOCKED", ("registry:attempt_scope_changed",))
            self._source_check(entry)
            # No method supplied by the policy or observation JSON is invoked.
            inspector = entry.inspector
            repository = inspector.inspect_repository()
            snapshot = inspector.lookup_snapshot_exact(ticket.snapshot_id)
            data = inspector.inspect_repository_data(ticket.snapshot_id)
            if (not isinstance(repository, dict)
                    or set(repository) != {"repository_id", "repository_accessible", "key_retrievable"}
                    or not isinstance(snapshot, dict)
                    or set(snapshot) != {"snapshot_id", "snapshot_exact_match"}
                    or not isinstance(data, dict)
                    or set(data) != {"snapshot_id", "repository_data_checked"}
                    or snapshot["snapshot_id"] != ticket.snapshot_id
                    or data["snapshot_id"] != ticket.snapshot_id):
                return RegisteredEvidenceResult("BLOCKED", ("registry:invalid_inspector_reply",))
            observation = {
                "schema": "backup-storage-observation/v1",
                "provider_fingerprint": entry.provider_fingerprint,
                "issuer_id": entry.issuer_id,
                "repository_id": repository["repository_id"],
                "snapshot_id": snapshot["snapshot_id"],
                "recovery_fingerprint": ticket.recovery_fingerprint,
                "compose_source_digest": ticket.compose_digest,
                "observed_at_unix": now_unix,
                "repository_accessible": repository["repository_accessible"],
                "snapshot_exact_match": snapshot["snapshot_exact_match"],
                "repository_data_checked": data["repository_data_checked"],
                "key_retrievable": repository["key_retrievable"],
            }
            checked = assess_storage_evidence(
                recovery_set, checkpoint, provider, observation,
                expected_provider_fingerprint=entry.provider_fingerprint,
                expected_issuer_id=entry.issuer_id, now_unix=now_unix,
                max_age_seconds=max_age_seconds, require_off_host=require_off_host,
            )
            return RegisteredEvidenceResult(checked.status, checked.blockers)
        except Exception:
            # Never leak raw adapter exception/credentials or grant permission.
            return RegisteredEvidenceResult("BLOCKED", ("registry:inspector_failed",))
