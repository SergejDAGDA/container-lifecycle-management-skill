"""Provider-neutral recovery-set and retention planning contracts.

This module is pure, read-only and EXPERIMENTAL. It cannot create snapshots,
restore state, delete backups, run Docker or authorize deployment. A passing
contract check is not evidence that backup/restore actually succeeded.

Do not place credentials, tokens, private file contents or raw environment
values in these structures. Validation returns static diagnostic labels only.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

SCHEMA = "recovery-set/v1"
HEX_SHA256 = re.compile(r"^sha256:[a-f0-9]{64}$")
SNAPSHOT_ID = re.compile(r"^[a-f0-9]{64}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
KINDS = frozenset({"database", "bind", "named_volume", "user_files",
                   "object_storage", "configuration", "secret_reference"})
BACKENDS = frozenset({"sqlite", "postgresql", "filesystem", "docker_volume",
                      "object_storage", "external_reference"})
CONSISTENCY = frozenset({"sqlite_backup_api", "pg_dump", "snapshot_quiesced",
                         "application_export", "immutable_reference"})
CHECKPOINT_CLASSES = frozenset({"PRE_DEPLOY", "PRE_UPGRADE", "PRE_MIGRATION",
                                "PRE_DECOMMISSION", "POST_VERIFIED_RELEASE",
                                "SCHEDULED_RECOVERY"})
PROOF_LEVELS = frozenset({"CAPTURED", "REPOSITORY_CHECKED", "RESTORE_TESTED"})
HOLD_REASONS = frozenset({"active_rollback", "pre_migration", "pre_decommission",
                          "last_known_good", "legal_hold", "manual_hold"})


@dataclass(frozen=True)
class RecoverySetValidation:
    valid: bool
    fingerprint: str | None
    errors: tuple[str, ...]


@dataclass(frozen=True)
class CheckpointValidation:
    valid: bool
    restore_tested: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class RetentionDryRun:
    """Advisory only: even eligible IDs cannot be deleted by this module."""

    permitted_candidates: tuple[str, ...]
    protected: tuple[tuple[str, str], ...]
    blockers: tuple[str, ...]


def _identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(IDENTIFIER.fullmatch(value))


def _sha(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX_SHA256.fullmatch(value))


def validate_recovery_set(document: Any) -> RecoverySetValidation:
    """Validate a complete *declaration*, never attest real recovery readiness.

    Canonical digest is of the validated JSON document. This is an immutable
    declaration fingerprint, not an image digest or backup verification proof.
    """
    errors: list[str] = []
    if not isinstance(document, dict):
        return RecoverySetValidation(False, None, ("recovery_set:not_mapping",))
    if document.get("schema") != SCHEMA:
        errors.append("recovery_set:schema")
    if not _identifier(document.get("application")):
        errors.append("recovery_set:application")
    compose = document.get("compose")
    if not isinstance(compose, dict) or not _identifier(compose.get("project")) or not _sha(compose.get("source_digest")):
        errors.append("recovery_set:compose_identity")
    images = document.get("images")
    if not isinstance(images, dict) or not images or any(not _identifier(k) or not _sha(v) for k,v in images.items()):
        errors.append("recovery_set:images")
    assets = document.get("assets")
    if not isinstance(assets, list) or not assets:
        errors.append("recovery_set:assets")
        assets = []
    seen: set[str] = set()
    for idx, asset in enumerate(assets):
        # Index only. Never echo untrusted asset identity or storage reference.
        if not isinstance(asset, dict):
            errors.append(f"recovery_set:asset_{idx}_mapping")
            continue
        aid = asset.get("id")
        kind = asset.get("kind")
        backend = asset.get("backend")
        consistency = asset.get("consistency")
        if not _identifier(aid) or (_identifier(aid) and aid in seen):
            errors.append(f"recovery_set:asset_{idx}_identity")
        if _identifier(aid):
            seen.add(aid)
        if not isinstance(kind, str) or kind not in KINDS or not isinstance(backend, str) or backend not in BACKENDS:
            errors.append(f"recovery_set:asset_{idx}_type")
        if not isinstance(consistency, str) or consistency not in CONSISTENCY:
            errors.append(f"recovery_set:asset_{idx}_consistency")
        if asset.get("recovery_required") is not True:
            errors.append(f"recovery_set:asset_{idx}_required")
        if not _identifier(asset.get("reference")):
            errors.append(f"recovery_set:asset_{idx}_reference")
        if kind == "database" and (backend not in ("sqlite", "postgresql") or consistency not in ("sqlite_backup_api", "pg_dump", "snapshot_quiesced", "application_export")):
            errors.append(f"recovery_set:asset_{idx}_database_consistency")
        if kind == "secret_reference" and (backend != "external_reference" or consistency != "immutable_reference"):
            errors.append(f"recovery_set:asset_{idx}_secret_boundary")
        if kind == "object_storage" and backend != "object_storage":
            errors.append(f"recovery_set:asset_{idx}_external_backend")
    if not any(a.get("kind") == "secret_reference" for a in assets if isinstance(a, dict)):
        errors.append("recovery_set:secret_recovery_reference_missing")
    allowed = {"schema", "application", "compose", "images", "assets"}
    if set(document) != allowed:
        errors.append("recovery_set:unknown_or_missing_fields")
    if isinstance(compose, dict) and set(compose) != {"project", "source_digest"}:
        errors.append("recovery_set:compose_unknown_fields")
    if any(isinstance(a, dict) and set(a) != {"id", "kind", "backend", "consistency", "reference", "recovery_required"} for a in assets):
        errors.append("recovery_set:asset_unknown_fields")
    if errors:
        return RecoverySetValidation(False, None, tuple(sorted(set(errors))))
    try:
        encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, OverflowError):
        return RecoverySetValidation(False, None, ("recovery_set:noncanonical",))
    return RecoverySetValidation(True, "sha256:" + hashlib.sha256(encoded).hexdigest(), ())


def validate_checkpoint(document: Any, *, recovery_fingerprint: str) -> CheckpointValidation:
    errors: list[str] = []
    if not _sha(recovery_fingerprint):
        errors.append("checkpoint:invalid_recovery_fingerprint")
    if not isinstance(document, dict):
        return CheckpointValidation(False, False, ("checkpoint:not_mapping",))
    if not (isinstance(document.get("id"), str) and SNAPSHOT_ID.fullmatch(document["id"])):
        errors.append("checkpoint:immutable_id")
    if document.get("recovery_fingerprint") != recovery_fingerprint:
        errors.append("checkpoint:recovery_fingerprint_mismatch")
    if not isinstance(document.get("class"), str) or document["class"] not in CHECKPOINT_CLASSES:
        errors.append("checkpoint:class")
    if not _identifier(document.get("provider")):
        errors.append("checkpoint:provider")
    if document.get("capture_complete") is not True:
        errors.append("checkpoint:capture_not_proven")
    if (not isinstance(document.get("holds"), list) or not all(isinstance(x, str) and x in HOLD_REASONS for x in document["holds"])):
        errors.append("checkpoint:holds")
    elif len(set(document["holds"])) != len(document["holds"]):
        errors.append("checkpoint:duplicate_holds")
    for field in ("repository_checked", "isolated_restore_tested", "application_smoke_passed"):
        if not isinstance(document.get(field), bool):
            errors.append("checkpoint:" + field + "_unknown")
    if document.get("application_smoke_passed") is True and document.get("isolated_restore_tested") is not True:
        errors.append("checkpoint:smoke_without_restore")
    if document.get("isolated_restore_tested") is True and document.get("repository_checked") is not True:
        errors.append("checkpoint:restore_without_repository_check")
    if set(document) != {"id", "recovery_fingerprint", "class", "provider", "capture_complete",
                         "holds", "repository_checked", "isolated_restore_tested", "application_smoke_passed"}:
        errors.append("checkpoint:unknown_or_missing_fields")
    passed = not errors
    proof = passed and all(document.get(field) is True for field in
                           ("repository_checked", "isolated_restore_tested", "application_smoke_passed"))
    return CheckpointValidation(passed, proof, tuple(sorted(set(errors))))


def plan_retention_dry_run(recovery_fingerprint: str, checkpoints: Any,
                           requested_ids: Any) -> RetentionDryRun:
    """Fail-closed non-mutating checkpoint retention preview.

    No dry-run output constitutes authorization to prune. Invalid inventory,
    unknown requested IDs, missing restore proofs or mismatched state identity
    block *all* candidates rather than assuming they can be removed.
    """
    if not _sha(recovery_fingerprint):
        return RetentionDryRun((), (), ("retention:invalid_recovery_fingerprint",))
    if (not isinstance(checkpoints, list) or not checkpoints
            or not isinstance(requested_ids, list)
            or any(not isinstance(x, str) or not SNAPSHOT_ID.fullmatch(x) for x in requested_ids)
            or len(set(requested_ids)) != len(requested_ids)):
        return RetentionDryRun((), (), ("retention:invalid_input",))
    snapshots: dict[str, dict] = {}
    for item in checkpoints:
        result = validate_checkpoint(item, recovery_fingerprint=recovery_fingerprint)
        if not result.valid or item["id"] in snapshots:
            return RetentionDryRun((), (), ("retention:invalid_checkpoint_inventory",))
        snapshots[item["id"]] = item
    if any(sid not in snapshots for sid in requested_ids):
        return RetentionDryRun((), (), ("retention:unknown_snapshot",))
    recoverable = {sid for sid, item in snapshots.items()
                   if validate_checkpoint(item, recovery_fingerprint=recovery_fingerprint).restore_tested}
    if not recoverable:
        return RetentionDryRun((), (), ("retention:no_restore_tested_checkpoint",))
    # No trustworthy timestamps/ordering: conservatively protect ALL verified
    # points until a separate evidence/age/approval contract is introduced.
    protected = []
    permitted = []
    for sid in requested_ids:
        item = snapshots[sid]
        reasons = set(item["holds"])
        if sid in recoverable:
            reasons.add("restore_tested_protected")
        if item["class"] in ("PRE_MIGRATION", "PRE_DECOMMISSION"):
            reasons.add("event_checkpoint_protected")
        if reasons:
            protected.append((sid, ",".join(sorted(reasons))))
        else:
            permitted.append(sid)
    return RetentionDryRun(tuple(permitted), tuple(protected), ())
