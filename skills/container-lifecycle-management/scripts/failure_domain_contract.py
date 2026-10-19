"""Experimental provider-neutral disaster fault-domain declaration gate.

Pure and read-only. It evaluates caller-supplied *claims*, not independent
verification. It never accesses Docker, snapshots, credentials, storage or
external services, and never authorizes failover, restore or data deletion.
All diagnostics are constant identifiers, with no untrusted values echoed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from recovery_contract import (
    IDENTIFIER, SNAPSHOT_ID, validate_checkpoint, validate_recovery_set,
)

SCHEMA = "failure-domain/v1"


@dataclass(frozen=True)
class FailureDomainAssessment:
    status: str
    blockers: tuple[str, ...]
    restore_authorized: bool = False
    off_host_proven: bool = False


def _id(value: Any) -> bool:
    return (isinstance(value, str) and value.lower() not in {"unknown", "none", "unresolved"}
            and bool(IDENTIFIER.fullmatch(value)))


def assess_disaster_recovery(
    recovery_set: Any,
    checkpoint: Any,
    topology: Any,
    availability: Any,
) -> FailureDomainAssessment:
    """Assess declaration completeness, not actual disaster-recovery proof.

    A passing result is CANDIDATE_ONLY, NOT RECOVERABLE or AUTHORIZED.
    Truthiness is deliberately not accepted for availability observations.
    """
    blockers: list[str] = []
    declared = validate_recovery_set(recovery_set)
    if not declared.valid or declared.fingerprint is None:
        blockers.append("disaster:invalid_recovery_set")
    fingerprint = declared.fingerprint or ""
    checked = validate_checkpoint(checkpoint, recovery_fingerprint=fingerprint)
    if not checked.valid or not checked.restore_tested:
        blockers.append("disaster:missing_restore_tested_checkpoint")
    if not isinstance(topology, dict) or set(topology) != {
        "schema", "recovery_fingerprint", "checkpoint_id", "source",
        "repository", "key_authority",
    } or topology.get("schema") != SCHEMA:
        blockers.append("disaster:invalid_topology")
        topology = {}
    if topology.get("recovery_fingerprint") != fingerprint or (
        not isinstance(checkpoint, dict)
        or topology.get("checkpoint_id") != checkpoint.get("id")
        or not isinstance(topology.get("checkpoint_id"), str)
        or not SNAPSHOT_ID.fullmatch(topology["checkpoint_id"])
    ):
        blockers.append("disaster:stale_checkpoint_identity")

    source = topology.get("source")
    repository = topology.get("repository")
    authority = topology.get("key_authority")
    if not isinstance(source, dict) or set(source) != {"node_id", "fault_domain"} or not all(
        _id(x) for x in source.values()
    ):
        blockers.append("disaster:invalid_source_boundary")
        source = {}
    if (not isinstance(repository, dict)
            or set(repository) != {"storage_id", "fault_domain", "storage_class"}
            or not _id(repository.get("storage_id"))
            or not _id(repository.get("fault_domain"))
            or repository.get("storage_class") not in {"on_host", "off_host"}):
        blockers.append("disaster:invalid_repository_boundary")
        repository = {}
    if (not isinstance(authority, dict)
            or set(authority) != {"authority_id", "fault_domain", "key_recovery"}
            or not _id(authority.get("authority_id"))
            or not _id(authority.get("fault_domain"))
            or authority.get("key_recovery") != "independent"):
        blockers.append("disaster:invalid_key_boundary")
        authority = {}

    if repository.get("storage_class") != "off_host":
        blockers.append("disaster:repository_not_off_host")
    domains = [source.get("fault_domain"), repository.get("fault_domain"),
               authority.get("fault_domain")]
    if None in domains or len(set(domains)) != 3:
        blockers.append("disaster:shared_or_unknown_fault_domain")

    if not isinstance(availability, dict) or set(availability) != {
        "source_unavailable", "repository_accessible", "key_retrievable",
        "snapshot_readable",
    }:
        blockers.append("disaster:invalid_availability")
        availability = {}
    for key in ("source_unavailable", "repository_accessible",
                "key_retrievable", "snapshot_readable"):
        if availability.get(key) is not True:
            blockers.append("disaster:" + key + "_unproven")

    if blockers:
        return FailureDomainAssessment("BLOCKED", tuple(sorted(set(blockers))))
    # These booleans and identities are caller assertions. A future trusted
    # provider must attest remote placement, access and restoration externally.
    return FailureDomainAssessment("CANDIDATE_ONLY", ())
