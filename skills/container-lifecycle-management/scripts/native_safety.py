"""Fail-closed semantic gates for extended native maintenance-policy records.

Pure, read-only validation. A complete *declaration* is never evidence that a
backup was restored or that an application migration is safe.
"""
from __future__ import annotations

import re
from typing import Any

ACTION_CLASSES = {"AUTO_SAFE", "AUTO_GATED", "PIN_ONLY"}
UNKNOWN = {"unknown", "unverified", "unresolved", "tbd", "todo", "not_checked", "none_recorded", ""}
IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
SECURITY_INVARIANTS = {
    "read_only_root", "no_new_privileges", "cap_drop_all",
    "read_only_docker_socket", "lan_only_binding",
}
USER_INVARIANT = re.compile(r"^user_[0-9]+_[0-9]+$")


def _defined(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        return value.strip().lower() not in UNKNOWN
    if isinstance(value, list):
        return bool(value) and all(_defined(x) for x in value)
    if isinstance(value, dict):
        return bool(value) and all(_defined(v) for v in value.values())
    return False


def safety_issues(service: dict) -> list[str]:
    """Return per-service blocking gaps without changing the original policy."""
    cls = service.get("policy_class")
    if not isinstance(cls, str) or cls not in ACTION_CLASSES:
        return []
    issues: list[str] = []
    def require(section: str, key: str, predicate, why: str) -> Any:
        entry = service.get(section)
        val = entry.get(key) if isinstance(entry, dict) else None
        if not predicate(val):
            issues.append(f"{section}.{key}: {why}")
        return val

    state = service.get("state_contract")
    require("state_contract", "completeness",
            lambda x: x == "complete", "automatic maintenance needs complete state")
    for key in ("binds", "named_volumes"):
        val = require("state_contract", key, lambda x: isinstance(x, list),
                      "must be an explicit list (including an explicit empty list)")
        if isinstance(val, list):
            seen_targets: set[str] = set()
            for i, item in enumerate(val):
                if not isinstance(item, dict):
                    issues.append(f"state_contract.{key}[{i}]: expected mapping")
                    continue
                target = item.get("target")
                selector = "source" if key == "binds" else "name"
                if not (_defined(item.get(selector)) and _defined(target)):
                    issues.append(f"state_contract.{key}[{i}]: missing source/name or target")
                if key == "binds" and item.get("mode") not in ("ro", "rw"):
                    issues.append(f"state_contract.binds[{i}].mode: must be ro or rw")
                if isinstance(target, str) and target in seen_targets:
                    issues.append(f"state_contract.{key}[{i}]: duplicated mount target")
                if isinstance(target, str):
                    seen_targets.add(target)
    if isinstance(state, dict):
        for key in ("databases", "uploaded_user_files", "account_state",
                    "instance_identity", "disposable_caches", "secrets"):
            val = state.get(key)
            # Explicit empty collections are valid descriptions of *absent*
            # state, but not evidence identities for recovery or rollback.
            if key == "instance_identity":
                # A single stable instance identity is not an empty collection.
                valid = (isinstance(val, str) and _defined(val)) or (
                    isinstance(val, dict) and _defined(val)
                )
            else:
                valid = (isinstance(val, list) and all(_defined(v) for v in val)) or _defined(val)
            if not valid:
                issues.append(f"state_contract.{key}: unresolved under complete state")
        dbs = state.get("databases")
        if not isinstance(dbs, list):
            issues.append("state_contract.databases: must be explicit list")
    image = require("image", "immutable_identity",
                    lambda v: isinstance(v, str) and bool(IMAGE_ID.fullmatch(v)),
                    "expected immutable sha256 identity")
    reproducible = require("deployment", "source_reproducible",
                           lambda v: v is True,
                           "must be strict boolean true, not just truthy")
    for section, key in (
        ("backup", "required"), ("topology", "mounts_invariant")
    ):
        require(section, key, lambda v: v is True,
                "must be strict boolean true for automatic actions")
    for key in ("recovery_mechanism", "freshness_requirement",
                "restore_verification_requirement"):
        require("backup", key, _defined, "explicit recovery/verification contract required")
    possible = require("migration", "possible", lambda v: type(v) is bool,
                       "must explicitly state boolean migration possibility")
    rbclass = require("migration", "rollback_class", _defined,
                      "migration rollback class must be declared")
    sr = require("migration", "state_rollback_required",
                 lambda v: type(v) is bool or (cls == "AUTO_GATED" and v == "possible"),
                 "state rollback semantics must be explicit")
    rollback_required = require("rollback", "state_rollback_may_be_required",
                                lambda v: type(v) is bool,
                                "must explicitly declare state rollback risk")
    for key in ("previous_image", "previous_image_identity", "deployment_source"):
        require("rollback", key, _defined, "rollback artifact/source identity is required")
    if cls == "AUTO_SAFE":
        if possible is not False or rbclass != "safe_image_and_source" or sr is not False or rollback_required is not False:
            issues.append("AUTO_SAFE: must prove migration-free safe image/source rollback")
    elif cls == "AUTO_GATED":
        if possible is True and rollback_required is not True:
            issues.append("AUTO_GATED: potential migration requires state-aware rollback boundary")
    elif cls == "PIN_ONLY":
        if possible is not False or rbclass != "source_pin_reversal" or sr is not False or rollback_required is not False:
            issues.append("PIN_ONLY: only reversible immutable source pin without migration allowed")
        require("image", "declared_reference", _defined, "exact target image pin required")
    for key in ("ports", "networks", "security_invariants"):
        val = require("topology", key, lambda v: isinstance(v, list),
                      "must be an explicit list (empty allowed for ports/security)")
        if isinstance(val, list) and not all(isinstance(x, str) and x.strip() for x in val):
            issues.append(f"topology.{key}: invalid entry")
        if key == "security_invariants" and isinstance(val, list):
            for invariant in val:
                if (not isinstance(invariant, str)
                        or invariant not in SECURITY_INVARIANTS
                        and USER_INVARIANT.fullmatch(invariant) is None):
                    # Never echo untrusted invariant values (which may contain secrets).
                    issues.append("topology.security_invariants: unsupported invariant (value withheld)")
    require("topology", "container_identity", _defined, "container identity missing")
    require("health", "docker_expectation",
            lambda v: v in ("healthy", "no_healthcheck"), "must be healthy or no_healthcheck")
    require("health", "stability_window_seconds",
            lambda v: type(v) is int and v > 0, "positive stability window required")
    require("smoke", "profile", _defined, "profile required")
    for key in ("generic", "service_specific"):
        val = require("smoke", key, lambda v: isinstance(v, list) and len(v) > 0,
                      "non-empty expected checks required")
        if isinstance(val, list) and not all(_defined(item) for item in val):
            issues.append(f"smoke.{key}: unresolved smoke check")
    return issues
