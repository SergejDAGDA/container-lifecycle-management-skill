"""Experimental provider-neutral BACKUP STORAGE evidence contract.

Pure and read-only: no imports selected from policy, no credentials, no
network, Docker, subprocess, deletion, backup capture or restore methods.
Input declarations and observation documents are UNTRUSTED claims. A future
reviewed provider adapter and independent witness must supply authenticated,
fresh evidence before any operational recovery decision.

Diagnostic output consists exclusively of static error identifiers.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from recovery_contract import (
    HEX_SHA256, IDENTIFIER, SNAPSHOT_ID,
    validate_checkpoint, validate_recovery_set,
)

PROVIDER_SCHEMA = "backup-storage-provider/v1"
OBSERVATION_SCHEMA = "backup-storage-observation/v1"
ENGINES = frozenset({"restic", "kopia", "borg", "other_oss"})
STORAGE_CLASSES = frozenset({"local", "off_host", "unknown"})
CAPABILITIES = frozenset({"exact_snapshot_lookup", "repository_data_check",
                          "isolated_restore_observation"})
PROVIDER_FIELDS = frozenset({
    "schema", "provider_id", "engine", "adapter_source_digest",
    "repository_id", "storage_class", "source_fault_domain",
    "repository_fault_domain", "key_authority_id", "key_fault_domain",
    "key_recovery_mode", "capabilities",
})
OBSERVATION_FIELDS = frozenset({
    "schema", "provider_fingerprint", "issuer_id", "repository_id",
    "snapshot_id", "recovery_fingerprint", "compose_source_digest",
    "observed_at_unix", "repository_accessible", "snapshot_exact_match",
    "repository_data_checked", "key_retrievable",
})
REQUIRED_CAPABILITIES = CAPABILITIES


class BackupStorageInspector(Protocol):
    """Future reviewed, read-only adapter surface; no implementation here.

    Never resolve or import an adapter from policy strings. All methods return
    observation data, not restoration permission or executable actions.
    """

    def inspect_repository(self) -> dict[str, Any]: ...

    def lookup_snapshot_exact(self, immutable_snapshot_id: str) -> dict[str, Any]: ...

    def inspect_repository_data(self, immutable_snapshot_id: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ProviderValidation:
    valid: bool
    fingerprint: str | None
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class StorageEvidenceAssessment:
    status: str
    blockers: tuple[str, ...]
    restore_authorized: bool = False
    off_host_proven: bool = False
    eligible_for_prune: bool = False


def _identifier(value: Any) -> bool:
    return (isinstance(value, str) and value.lower() not in
            {"unknown", "none", "unresolved", "missing"}
            and bool(IDENTIFIER.fullmatch(value)))


def _digest(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX_SHA256.fullmatch(value))


def validate_storage_provider(value: Any) -> ProviderValidation:
    """Validate provider *declaration* and canonical identity, never reality."""
    errors: list[str] = []
    if not isinstance(value, dict):
        return ProviderValidation(False, None, ("storage:provider_not_mapping",))
    if set(value) != PROVIDER_FIELDS or value.get("schema") != PROVIDER_SCHEMA:
        errors.append("storage:provider_schema_or_fields")
    for name in ("provider_id", "repository_id", "source_fault_domain",
                 "repository_fault_domain", "key_authority_id", "key_fault_domain"):
        if not _identifier(value.get(name)):
            errors.append("storage:invalid_" + name)
    if not isinstance(value.get("engine"), str) or value["engine"] not in ENGINES:
        errors.append("storage:invalid_engine")
    if not _digest(value.get("adapter_source_digest")):
        errors.append("storage:invalid_adapter_pin")
    if not isinstance(value.get("storage_class"), str) or value["storage_class"] not in STORAGE_CLASSES:
        errors.append("storage:invalid_storage_class")
    if value.get("key_recovery_mode") not in ("independent", "unverified"):
        errors.append("storage:invalid_key_recovery_mode")
    caps = value.get("capabilities")
    if (not isinstance(caps, list) or
            any(not isinstance(x, str) or x not in CAPABILITIES for x in caps)):
        errors.append("storage:invalid_capabilities")
    elif len(caps) != len(set(caps)):
        errors.append("storage:invalid_capabilities")
    elif set(caps) != REQUIRED_CAPABILITIES:
        errors.append("storage:missing_required_capabilities")
    if errors:
        return ProviderValidation(False, None, tuple(sorted(set(errors))))
    try:
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, OverflowError):
        return ProviderValidation(False, None, ("storage:noncanonical",))
    return ProviderValidation(True, "sha256:" + hashlib.sha256(canonical).hexdigest(), ())


def assess_storage_evidence(
    recovery_set: Any,
    checkpoint: Any,
    provider: Any,
    observation: Any,
    *,
    expected_provider_fingerprint: Any,
    expected_issuer_id: Any,
    now_unix: Any,
    max_age_seconds: Any = 900,
    require_off_host: bool = True,
) -> StorageEvidenceAssessment:
    """Fail closed on scope, identity, freshness and declared failure domains.

    Even all matching declarations and booleans produce only CANDIDATE_ONLY.
    Callers are responsible for trusted clocks, verified adapter registrations,
    authentic independent observations and real remote restore proof.
    """
    errors: list[str] = []
    recovery = validate_recovery_set(recovery_set)
    if not recovery.valid or recovery.fingerprint is None:
        errors.append("storage:invalid_recovery_set")
    recovery_fingerprint = recovery.fingerprint or ""
    proof = validate_checkpoint(checkpoint, recovery_fingerprint=recovery_fingerprint)
    if not proof.valid or not proof.restore_tested:
        errors.append("storage:missing_restore_tested_checkpoint")
    descriptor = validate_storage_provider(provider)
    if not descriptor.valid:
        errors.append("storage:invalid_provider")
    if (not isinstance(checkpoint, dict) or not isinstance(provider, dict)
            or checkpoint.get("provider") != provider.get("engine")):
        errors.append("storage:checkpoint_provider_mismatch")
    if (not _digest(expected_provider_fingerprint)
            or expected_provider_fingerprint != descriptor.fingerprint):
        errors.append("storage:provider_pin_mismatch")
    if not _identifier(expected_issuer_id):
        errors.append("storage:missing_trusted_issuer_reference")
    if not isinstance(observation, dict) or set(observation) != OBSERVATION_FIELDS or (
            isinstance(observation, dict) and observation.get("schema") != OBSERVATION_SCHEMA):
        errors.append("storage:observation_schema_or_fields")
        observation = {}
    for name in ("provider_fingerprint", "repository_id", "snapshot_id",
                 "recovery_fingerprint", "compose_source_digest", "issuer_id"):
        if not isinstance(observation.get(name), str):
            errors.append("storage:invalid_observation_" + name)
    if observation.get("provider_fingerprint") != descriptor.fingerprint:
        errors.append("storage:observation_provider_mismatch")
    if observation.get("repository_id") != (
            provider.get("repository_id") if isinstance(provider, dict) else None):
        errors.append("storage:observation_repository_mismatch")
    if (not isinstance(checkpoint, dict)
            or observation.get("snapshot_id") != checkpoint.get("id")
            or not isinstance(observation.get("snapshot_id"), str)
            or not SNAPSHOT_ID.fullmatch(observation["snapshot_id"])):
        errors.append("storage:observation_snapshot_mismatch")
    if observation.get("recovery_fingerprint") != recovery_fingerprint:
        errors.append("storage:observation_recovery_mismatch")
    compose = recovery_set.get("compose") if isinstance(recovery_set, dict) else None
    if (not isinstance(compose, dict)
            or observation.get("compose_source_digest") != compose.get("source_digest")):
        errors.append("storage:observation_source_mismatch")
    if observation.get("issuer_id") != expected_issuer_id:
        errors.append("storage:untrusted_issuer_claim")
    for name in ("repository_accessible", "snapshot_exact_match",
                 "repository_data_checked", "key_retrievable"):
        if observation.get(name) is not True:
            errors.append("storage:" + name + "_unproven")
    if (type(now_unix) is not int or now_unix < 0
            or type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 86400
            or type(observation.get("observed_at_unix")) is not int
            or observation["observed_at_unix"] < 0
            or observation["observed_at_unix"] > now_unix
            or now_unix - observation["observed_at_unix"] > max_age_seconds):
        errors.append("storage:stale_or_invalid_observation")
    if isinstance(provider, dict):
        if provider.get("source_fault_domain") == provider.get("repository_fault_domain"):
            errors.append("storage:shared_source_repository_domain")
        if (provider.get("key_fault_domain") in
                (provider.get("source_fault_domain"), provider.get("repository_fault_domain"))):
            errors.append("storage:nonindependent_key_domain")
        if provider.get("key_recovery_mode") != "independent":
            errors.append("storage:key_recovery_not_independent")
        if require_off_host and provider.get("storage_class") != "off_host":
            errors.append("storage:off_host_required")
        if provider.get("storage_class") == "unknown":
            errors.append("storage:unknown_storage_location")
    if type(require_off_host) is not bool:
        errors.append("storage:invalid_scope")
    if errors:
        return StorageEvidenceAssessment("BLOCKED", tuple(sorted(set(errors))))
    return StorageEvidenceAssessment("CANDIDATE_ONLY", ())
