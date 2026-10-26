"""Experimental, pure migration-aware refusal contract.

Never invokes Docker, executes a rollback, restores state, or authorizes a
deployment. Inputs are assertions supplied by a caller, NOT independently
trusted observations. A future trusted executor must collect and bind them.
Diagnostics are static codes only, never raw runtime or policy values.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from recovery_contract import validate_checkpoint, validate_recovery_set

SCHEMA_REVISION = re.compile(r"^v[1-9][0-9]{0,3}$")


@dataclass(frozen=True)
class RollbackDecision:
    status: str
    image_only_allowed: bool
    recovery_checkpoint_id: str | None
    blockers: tuple[str, ...]
    next_action: str


def evaluate_image_only_rollback(
    *,
    recovery_set: Any,
    checkpoint: Any,
    expected_fingerprint: Any,
    expected_runtime: Any,
    observed_runtime: Any,
    rollback_images: Any,
    migration_scope: Any,
    baseline_schema: Any,
    observed_schema: Any,
    interrupted_after_commit: Any,
) -> RollbackDecision:
    """Evaluate a known incompatible migration, without authorizing ANY action.

    RECOVERY_REQUIRED identifies a validated PRE_MIGRATION proof for a
    separately authorized state-aware recovery. It is never a restore command.
    BLOCKED means the evidence is inadequate even to identify that path.
    """
    errors: list[str] = []
    declaration = validate_recovery_set(recovery_set)
    if not declaration.valid or declaration.fingerprint is None:
        errors.append("rollback:invalid_recovery_set")
    if (not isinstance(expected_fingerprint, str)
            or expected_fingerprint != declaration.fingerprint):
        errors.append("rollback:stale_recovery_identity")

    proof = validate_checkpoint(checkpoint, recovery_fingerprint=expected_fingerprint)
    if not proof.valid or not proof.restore_tested:
        errors.append("rollback:missing_restore_tested_checkpoint")
    if isinstance(checkpoint, dict) and (
        checkpoint.get("class") != "PRE_MIGRATION"
        or not isinstance(checkpoint.get("holds"), list)
        or "pre_migration" not in checkpoint["holds"]
    ):
        errors.append("rollback:pre_migration_protection_missing")

    if isinstance(recovery_set, dict):
        db_ids = [a["id"] for a in recovery_set.get("assets", [])
                  if isinstance(a, dict) and a.get("kind") == "database"
                  and isinstance(a.get("id"), str)]
        original_images = recovery_set.get("images")
        compose = recovery_set.get("compose")
        source_digest = compose.get("source_digest") if isinstance(compose, dict) else None
    else:
        db_ids, original_images, source_digest = [], None, None

    if (not db_ids or not isinstance(migration_scope, list) or not migration_scope
            or any(not isinstance(x, str) for x in migration_scope)
            or len(set(migration_scope)) != len(migration_scope)
            or set(migration_scope) != set(db_ids)):
        errors.append("rollback:unbounded_migration_scope")

    if not isinstance(rollback_images, dict) or rollback_images != original_images:
        errors.append("rollback:wrong_rollback_image_identity")

    required_runtime_keys = {"compose_source_digest", "images", "schema_revision"}
    for label, runtime in (("expected", expected_runtime), ("observed", observed_runtime)):
        if (not isinstance(runtime, dict)
                or set(runtime) != required_runtime_keys
                or runtime.get("compose_source_digest") != source_digest
                or not isinstance(runtime.get("images"), dict)
                or set(runtime["images"]) != set(original_images or {})
                or any(not isinstance(v, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", v)
                       for v in runtime["images"].values())
                or not isinstance(runtime.get("schema_revision"), str)
                or not SCHEMA_REVISION.fullmatch(runtime["schema_revision"])):
            errors.append("rollback:invalid_" + label + "_runtime")

    if expected_runtime != observed_runtime:
        errors.append("rollback:stale_runtime_identity")
    if (not isinstance(baseline_schema, str)
            or not SCHEMA_REVISION.fullmatch(baseline_schema)
            or not isinstance(observed_schema, str)
            or not SCHEMA_REVISION.fullmatch(observed_schema)
            or baseline_schema == observed_schema
            or not isinstance(observed_runtime, dict)
            or observed_runtime.get("schema_revision") != observed_schema):
        errors.append("rollback:incompatible_schema_not_proven")
    if interrupted_after_commit is not True:
        errors.append("rollback:interruption_not_proven")

    if errors:
        return RollbackDecision("BLOCKED", False, None, tuple(sorted(set(errors))),
                                "revalidate_and_obtain_independent_recovery_evidence")
    return RollbackDecision("RECOVERY_REQUIRED", False, checkpoint["id"],
                            ("rollback:image_only_schema_incompatible",),
                            "plan_separately_authorized_state_aware_recovery")
