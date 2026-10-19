"""Fail-closed, opt-in binding of project safety rules to a trusted adapter.

The policy is inert data: no dynamic imports, code paths, URLs, shell commands,
downloads, installation, or untrusted plugin entrypoints can be used here.

A consuming project must provide an already reviewed and independently verified
adapter through the host application's trusted in-process registry. Matching a
declared digest here checks a PIN, not the provenance of Python source bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Any
import re

API = "maintain-server-containers/safety-adapter/v1"
IDENTITY = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
STATUSES = frozenset({"PASS", "BLOCK", "UNRESOLVED", "ERROR"})
MANIFEST_KEYS = frozenset({"api", "id", "version", "digest", "required"})


@dataclass(frozen=True)
class TrustedSafetyAdapter:
    """Created only by a consuming project's *trusted* integration code."""
    adapter_id: str
    version: str
    digest: str
    claims: frozenset[str]
    check_global: Callable[[Mapping[str, Any]], Mapping[str, str]]
    # Optional later-phase service validation is additive: never removes core gates.
    check_service: Callable[[Mapping[str, Any], Mapping[str, Any], str], Mapping[str, str]] | None = None


def validate_adapter_claims(
    policy: Mapping[str, Any],
    core_invariants: frozenset[str],
    registry: Mapping[str, TrustedSafetyAdapter] | None = None,
) -> list[str]:
    """Validate all additional invariant claims; only PASS counts as supported.

    A missing adapter, bad pin, unknown claim, unexpected outcome, or exception
    is a validation error. Errors deliberately omit untrusted key/value data.
    """
    issues: list[str] = []
    declared = policy.get("safety_invariants")
    if not isinstance(declared, dict):
        return ["safety_invariants must be a mapping"]
    extras = set(declared).difference(core_invariants)
    if any(not isinstance(key, str) or not IDENTITY.fullmatch(key) for key in extras):
        issues.append("unknown global safety invariant has invalid identifier (withheld)")
        return issues

    manifest = policy.get("safety_adapter")
    if manifest is None:
        if extras:
            issues.append("unsupported global safety invariant: trusted, pinned safety adapter required (identifier withheld)")
        return issues
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
        return ["safety_adapter manifest fields invalid (values withheld)"]
    if manifest.get("api") != API:
        issues.append("safety_adapter API incompatible")
    if not isinstance(manifest.get("id"), str) or not IDENTITY.fullmatch(manifest["id"]):
        issues.append("safety_adapter identifier invalid (withheld)")
    if not isinstance(manifest.get("version"), str) or not VERSION.fullmatch(manifest["version"]):
        issues.append("safety_adapter version invalid")
    if not isinstance(manifest.get("digest"), str) or not DIGEST.fullmatch(manifest["digest"]):
        issues.append("safety_adapter digest invalid")
    if manifest.get("required") is not True:
        issues.append("safety_adapter must be required=true")
    if issues:
        return issues
    registry = registry or {}
    adapter = registry.get(manifest["id"])
    if not isinstance(adapter, TrustedSafetyAdapter):
        return ["trusted safety adapter not registered"]
    if (adapter.adapter_id != manifest["id"] or adapter.version != manifest["version"]
            or adapter.digest != manifest["digest"]):
        return ["trusted safety adapter identity/version/digest mismatch"]
    if (not isinstance(adapter.claims, frozenset)
            or any(not isinstance(key, str) or not IDENTITY.fullmatch(key)
                   for key in adapter.claims)
            or adapter.claims != frozenset(extras)):
        return ["trusted safety adapter claim coverage mismatch"]
    if not callable(adapter.check_global):
        return ["trusted safety adapter global checker missing"]
    try:
        result = adapter.check_global(policy)
    except Exception:
        return ["trusted safety adapter global checker failed (details withheld)"]
    if not isinstance(result, dict) or set(result) != extras:
        return ["trusted safety adapter results incomplete or unexpected"]
    for key, status in result.items():
        if not isinstance(status, str) or status not in STATUSES:
            return ["trusted safety adapter returned invalid result"]
        if status != "PASS":
            issues.append("trusted safety adapter has non-passing global invariant")
    return issues


def validate_adapter_service(
    adapter: TrustedSafetyAdapter,
    service: Mapping[str, Any],
    evidence: Mapping[str, Any],
    phase: str
) -> list[str]:
    """Optional additive checks for the execution phase, not an authorization."""
    if not isinstance(adapter, TrustedSafetyAdapter) or not callable(adapter.check_service):
        return ["trusted safety adapter service validator unavailable"]
    if phase not in ("plan", "pre_mutation", "post_deploy", "restore"):
        return ["safety adapter validation phase invalid"]
    try:
        results = adapter.check_service(service, evidence, phase)
    except Exception:
        return ["trusted safety adapter service validator failed (details withheld)"]
    if not isinstance(results, dict) or not results:
        return ["trusted safety adapter service results missing"]
    if (not isinstance(adapter.claims, frozenset)
            or not adapter.claims
            or any(not isinstance(k, str) or not IDENTITY.fullmatch(k)
                   for k in adapter.claims)):
        return ["trusted safety adapter service claims invalid"]
    if any(not isinstance(k, str) or not IDENTITY.fullmatch(k)
           or not isinstance(v, str) or v not in STATUSES for k, v in results.items()):
        return ["trusted safety adapter service results malformed"]
    # Every claimed rule must have a result for *this* service and phase.
    # An unrelated passing rule cannot disguise an omitted safety check.
    if set(results) != adapter.claims:
        return ["trusted safety adapter service result claim coverage mismatch"]
    return [] if all(v == "PASS" for v in results.values()) else [
        "trusted safety adapter service check did not pass"
    ]
