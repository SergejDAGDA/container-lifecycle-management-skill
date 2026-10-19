#!/usr/bin/env python3
"""Read-only policy checks for the container-lifecycle-management Agent Skill.

No command in this module changes Docker, Compose, images, files, or networks.
A plan is not an authorization or proof of backup/recovery readiness.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from release_management import public_release_management

POLICIES = {"AUTO_SAFE", "AUTO_GATED", "MANUAL", "PIN_ONLY", "NO_TOUCH"}
OWNERS = {"sandbox", "application_project", "external_admin", "unknown"}
POLICY_VERSION = "1"
NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")

SUPPORTED = {"validate", "audit", "status", "plan"}

# Fail closed on unrecognized portable v1 rules rather than treating project
# extensions or undeclared approval gates as verified policy.
PORTABLE_ROOT_FIELDS = frozenset({"schema_version", "services"})
PORTABLE_SERVICE_FIELDS = frozenset({
    "name", "policy", "ownership", "reason", "deployment", "image",
    "target", "state", "backup", "rollback", "health", "smoke",
    "release_management",
})
PORTABLE_SECTION_FIELDS = {
    "deployment": frozenset({"compose_file", "project", "service"}),
    "image": frozenset({"current"}),
    "target": frozenset({"image"}),
    "state": frozenset({"complete", "binds", "volumes", "databases",
                        "user_files", "secret_refs"}),
    "backup": frozenset({"required"}),
    "rollback": frozenset({"class"}),
    "health": frozenset({"container"}),
    "smoke": frozenset({"profile"}),
}

# Deliberately minimal Docker inspect output: never request Config.Env,
# labels, arguments, host security metadata or the raw full inspect object.
# Static Go template text is code-owned and not selected by the YAML policy.
PORTABLE_INSPECT_TEMPLATE = (
    '{"Id":{{json .Id}},"Image":{{json .Image}},'
    '"Config":{"Image":{{json .Config.Image}}},'
    '"State":{"Running":{{json .State.Running}},'
    '"Health":{{with .State.Health}}{"Status":{{json .Status}}}'
    '{{else}}null{{end}}},'
    '"Mounts":[{{range $i, $mount := .Mounts}}'
    '{{if $i}},{{end}}'
    '{"Type":{{json $mount.Type}},"Source":{{json $mount.Source}},'
    '"Name":{{json $mount.Name}},"Destination":{{json $mount.Destination}},'
    '"RW":{{json $mount.RW}}}'
    '{{end}}]}'
)


class PolicyError(Exception):
    pass


def _mapping(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise PolicyError(f"{label} must be a mapping")
    return value


def _list(value: Any, label: str) -> list:
    if not isinstance(value, list):
        raise PolicyError(f"{label} must be a list")
    return value


def load_policy(path: Path) -> dict:
    if not path.is_file():
        raise PolicyError("Policy file does not exist")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise PolicyError("Invalid JSON policy") from exc
    else:
        try:
            import yaml
        except ImportError as exc:
            raise PolicyError("YAML policy requires PyYAML in the selected Python. Run doctor.py with that interpreter and use an existing reviewed local environment. Do not install packages on the inspected server for a read-only audit") from exc
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeError) as exc:
            raise PolicyError("Invalid YAML policy") from exc
    return _mapping(data, "Policy")


def normalize(data: dict) -> tuple[list[dict], list[str]]:
    """Normalize the documented portable v1 schema. Never assume unknown fields are safe."""
    errors: list[str] = []
    if any(not isinstance(k, str) for k in data):
        errors.append("portable policy top-level field keys must be strings")
    if set(data).difference(PORTABLE_ROOT_FIELDS):
        errors.append("unsupported portable top-level fields (names and values withheld)")
    version = data.get("schema_version")
    if type(version) is not str or version != POLICY_VERSION:
        errors.append("schema_version must be '1' (explicit migration required)")
    raw = data.get("services")
    if isinstance(raw, dict):
        # Named mapping accepted for simple project configuration.
        entries = []
        for key, value in raw.items():
            if isinstance(value, dict) and "name" not in value:
                entry = dict(value)
                entry["name"] = key
                entries.append(entry)
            else:
                entries.append(value)
    elif isinstance(raw, list):
        entries = raw
    else:
        raise PolicyError("services must be a list or a named mapping")
    normalized: list[dict] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"services[{index}] must be a mapping")
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            errors.append(f"services[{index}].name is invalid")
            continue
        if name in seen:
            errors.append(f"{name}: duplicate service identity")
            continue
        seen.add(name)
        policy = entry.get("policy")
        ownership = entry.get("ownership")
        if not isinstance(policy, str) or policy not in POLICIES:
            errors.append(f"{name}: invalid or missing policy")
        if not isinstance(ownership, str) or ownership not in OWNERS:
            errors.append(f"{name}: invalid or missing ownership")
        if any(not isinstance(key, str) for key in entry):
            errors.append(f"{name}: service field keys must all be strings")
        if set(entry).difference(PORTABLE_SERVICE_FIELDS):
            errors.append(f"{name}: unsupported portable service fields (names and values withheld)")
        for field, allowed in PORTABLE_SECTION_FIELDS.items():
            if field not in entry:
                continue
            section = entry[field]
            if not isinstance(section, dict):
                errors.append(f"{name}: {field} must be a mapping")
            else:
                if any(not isinstance(k, str) for k in section):
                    errors.append(f"{name}: {field} keys must be strings")
                if set(section).difference(allowed):
                    errors.append(f"{name}: unsupported {field} fields (names and values withheld)")
        from release_management import validate_release_management
        errors.extend(validate_release_management(entry, class_field="policy"))
        normalized.append(entry)
    return normalized, errors


def validate_service(service: dict) -> list[str]:
    name = service["name"]
    policy = service.get("policy")
    owner = service.get("ownership")
    issues: list[str] = []
    if isinstance(policy, str) and policy in {"MANUAL", "NO_TOUCH"}:
        return issues
    if isinstance(owner, str) and owner in {"external_admin", "unknown"}:
        issues.append("ownership not eligible for automated maintenance")
    state = service.get("state", {})
    if not isinstance(state, dict):
        state = {}
    if state.get("complete") is not True:
        issues.append("state contract not proven complete")
    for key in ("binds", "volumes", "databases", "user_files", "secret_refs"):
        if not isinstance(state.get(key), list):
            issues.append(f"state.{key} must be an explicit list, even when empty")
    deploy = service.get("deployment", {})
    if not isinstance(deploy, dict) or not all(
        isinstance(deploy.get(k), str) and deploy[k].strip()
        for k in ("compose_file", "project", "service")
    ):
        issues.append("reproducible Compose deployment identity incomplete")
    if not isinstance(service.get("image"), dict) or not isinstance(
        service["image"].get("current"), str
    ):
        issues.append("current image identity missing")
    if policy != "PIN_ONLY":
        target = service.get("target", {})
        if not isinstance(target, dict) or not isinstance(target.get("image"), str):
            issues.append("explicit target image not specified")
    else:
        if not isinstance(service.get("target"), dict) or not isinstance(
            service["target"].get("image"), str
        ):
            issues.append("explicit immutable pin target missing")
    rollback = service.get("rollback", {})
    if not isinstance(rollback, dict):
        rollback = {}
    if rollback.get("class") not in (
        "image_only", "state_restore_required", "unknown"
    ):
        issues.append("rollback classification missing")
    if policy == "AUTO_SAFE" and rollback.get("class") != "image_only":
        issues.append("AUTO_SAFE requires proven image-only rollback")
    if policy == "AUTO_GATED" and rollback.get("class") == "unknown":
        issues.append("AUTO_GATED rollback contract unresolved")
    if not isinstance(service.get("health"), dict):
        issues.append("health contract missing")
    if not isinstance(service.get("smoke"), dict):
        issues.append("smoke profile contract missing")
    backup = service.get("backup", {})
    if not isinstance(backup, dict):
        backup = {}
    if type(backup.get("required")) is not bool:
        issues.append("backup requirement not declared")
    if policy == "AUTO_GATED" and backup.get("required") is not True:
        issues.append("AUTO_GATED requires backup gate")
    return issues


def docker_snapshot(service: dict) -> dict:
    """Read only a uniquely identified Compose service. No shell and no mutation."""
    deployment = service.get("deployment", {})
    if not isinstance(deployment, dict):
        return {"status": "unverified"}
    project = deployment.get("project")
    name = deployment.get("service")
    if not all(isinstance(s, str) and NAME.fullmatch(s) for s in (project, name)):
        return {"status": "unverified"}
    command = ["docker", "ps", "-a", "--quiet",
               "--filter", f"label=com.docker.compose.project={project}",
               "--filter", f"label=com.docker.compose.service={name}"]
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=15, check=False)
        if proc.returncode:
            return {"status": "unverified", "reason": "docker unavailable"}
        if not isinstance(proc.stdout, str):
            return {"status": "unverified", "reason": "container listing unavailable"}
        ids = [s for s in proc.stdout.splitlines() if s]
        if len(ids) != 1:
            return {"status": "unverified", "reason": "expected exactly one Compose container"}
        proc = subprocess.run(["docker", "inspect", "--format",
                               PORTABLE_INSPECT_TEMPLATE, ids[0]],
                              text=True, capture_output=True, timeout=15, check=False)
        if proc.returncode:
            return {"status": "unverified", "reason": "inspect unavailable"}
        obj = json.loads(proc.stdout)
        # Docker inspect is external input. Its shape is not guaranteed; do
        # not allow malformed values to escape as AttributeError or accidentally
        # be promoted to independently verified runtime evidence.
        if not isinstance(obj, dict):
            raise ValueError("malformed Docker inspect root")
        state = obj.get("State")
        config = obj.get("Config")
        mounts = obj.get("Mounts")
        if not isinstance(state, dict) or not isinstance(config, dict):
            raise ValueError("malformed Docker state/config")
        if not isinstance(mounts, list):
            raise ValueError("malformed Docker mounts")
        if not (isinstance(obj.get("Image"), str)
                and isinstance(config.get("Image"), str)
                and type(state.get("Running")) is bool
                and isinstance(obj.get("Id"), str)):
            raise ValueError("incomplete Docker runtime identity")
        health = state.get("Health")
        if health is not None and not isinstance(health, dict):
            raise ValueError("malformed Docker health")
        if health is not None and not isinstance(health.get("Status"), str):
            raise ValueError("malformed Docker health status")
        normalized_mounts = set()
        for m in mounts:
            if not isinstance(m, dict):
                raise ValueError("malformed Docker mount")
            if (not isinstance(m.get("Type"), str)
                    or not isinstance(m.get("Destination"), str)
                    or type(m.get("RW")) is not bool):
                raise ValueError("malformed Docker mount attributes")
            source = m.get("Name") or m.get("Source")
            if not isinstance(source, str):
                raise ValueError("malformed Docker mount source")
            normalized_mounts.add((m["Type"], source, m["Destination"], not m["RW"]))
        return {
            "status": "verified",
            "image_id": obj["Image"],
            "configured_image": config["Image"],
            "running": state["Running"],
            "health": health["Status"] if health is not None else "none",
            "container_id": obj["Id"],
            "mounts": sorted(normalized_mounts, key=str),
        }
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return {"status": "unverified", "reason": "runtime inspection unavailable"}


def assessment(service: dict, runtime: dict | None) -> dict:
    issues = validate_service(service)
    policy = service.get("policy")
    if policy == "NO_TOUCH":
        classification = "EXCLUDED"
    elif policy == "MANUAL":
        classification = "MANUAL_REVIEW"
    elif issues:
        classification = "BLOCKED"
    else:
        classification = "CANDIDATE"
    r = runtime if isinstance(runtime, dict) else {
        "status": "not_checked" if runtime is None else "unverified"
    }
    if runtime is not None and not isinstance(runtime, dict):
        issues.append("runtime evidence format invalid")
    if classification == "CANDIDATE" and r.get("status") != "verified":
        issues.append("current runtime not independently verified")
        classification = "BLOCKED"
    if classification == "CANDIDATE":
        expected = service.get("image", {}).get("current")
        observed = r.get("configured_image")
        if expected != observed:
            issues.append("configured image differs from policy (resolve before update)")
            classification = "BLOCKED"
        if not r.get("running"):
            issues.append("service is not currently running")
            classification = "BLOCKED"
    if classification == "CANDIDATE":
        # A generic YAML declaration is never proof of recovery or smoke-test execution.
        issues.append("live backup, upstream, topology, and smoke gates need execution-time proof")
        classification = "GATED"
    return {
        "name": service["name"],
        "policy": policy,
        "ownership": service.get("ownership"),
        "classification": classification,
        "issues": issues,
        "runtime": {
            "status": r.get("status"),
            "running": r.get("running"),
            "health": r.get("health"),
            "configured_image": r.get("configured_image"),
            "image_id": r.get("image_id")
        },
        "release_management": public_release_management(service),
        "proposed_target": (service.get("target", {}).get("image")
                            if isinstance(service.get("target"), dict) else None),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only container maintenance policy tool")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--live", action="store_true", help="Inspect Docker read-only")
    parser.add_argument("--runtime-json", type=Path, help="Synthetic/runtime evidence for testing")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("operation", choices=sorted(SUPPORTED))
    args = parser.parse_args(argv)
    try:
        data = load_policy(args.policy)
        if (isinstance(data.get("schema"), str)
                and data["schema"].endswith("-maintenance/v1")):
            from native_policy import structure, assess_native
            services, errors, warnings = structure(data)
            if args.runtime_json:
                raise PolicyError("native policy adapter does not accept synthetic runtime evidence")
            if args.operation == "validate":
                result = {
                    "schema": data["schema"],
                    "services": len(services),
                    "valid": not errors,
                    "errors": errors,
                    "warnings": warnings,
                    "note": "Structural and semantic policy checks are not backup/restore or runtime verification."
                }
            else:
                if errors:
                    # Preserve a useful per-service inventory while guaranteeing that
                    # an invalid policy never triggers even read-only live inspection.
                    records = []
                    for svc in services:
                        service_name = svc["name"]
                        cls = svc.get("policy_class")
                        classification = ("EXCLUDED" if cls == "NO_TOUCH" else
                                          "MANUAL_REVIEW" if cls == "MANUAL" else "BLOCKED")
                        problems = [e for e in errors if e.startswith(service_name + ":")]
                        if cls not in ("MANUAL", "NO_TOUCH"):
                            problems.append("policy invalid: runtime inspection skipped; update forbidden")
                        records.append({
                            "name": service_name, "policy": cls,
                            "ownership": svc.get("ownership"),
                            "classification": classification, "issues": problems,
                            "runtime": {"status": "NOT_CHECKED"},
                            "target_candidate": None,
                            "release_management": public_release_management(svc)
                        })
                else:
                    records = assess_native(data, services, live=args.live)
                result = {
                    "operation": args.operation,
                    "read_only": True,
                    "schema": data["schema"],
                    "policy_valid": not errors,
                    "errors": errors,
                    "warnings": warnings,
                    "services": records,
                    "note": "All candidates remain gated until release, backup and recovery evidence is verified."
                }
            if args.format == "json":
                print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
            else:
                for error in errors:
                    print(f"ERROR: {error}")
                if args.operation == "validate":
                    print(f"Native policy structural validation: {'PASS' if not errors else 'FAIL'} "
                          f"({len(services)} services)")
                else:
                    for record in result["services"]:
                        print(f"{record['name']}: {record['classification']} "
                              f"[{record['policy']}]")
                        for issue in record["issues"]:
                            print(f"  - {issue}")
                    print("READ-ONLY. No changes made.")
                for warning in warnings:
                    print(f"NOTE: {warning}")
            return 2 if errors else 0
        services, errors = normalize(data)
        if args.live and args.runtime_json:
            raise PolicyError("--live and --runtime-json cannot be combined")
        # Resolve all declared policy blockers *before* any access to Docker
        # or synthetic runtime inputs. A malformed policy must never initiate
        # even read-only live inspection.
        service_errors = {}
        for service in services:
            service_class = service.get("policy")
            if isinstance(service_class, str) and service_class in {"MANUAL", "NO_TOUCH"}:
                service_errors[service["name"]] = []
                continue
            problems = validate_service(service)
            service_errors[service["name"]] = problems
            errors.extend(f"{service['name']}: {issue}" for issue in problems)
        evidence = {}
        if not errors and args.runtime_json:
            evidence = _mapping(json.loads(args.runtime_json.read_text(encoding="utf-8")),
                                "Runtime evidence")
            if any(not isinstance(key, str) or not isinstance(value, dict)
                   for key, value in evidence.items()):
                raise PolicyError("Synthetic runtime evidence must map service names to mappings")
        if args.operation == "validate":
            result = {"schema_version": POLICY_VERSION, "services": len(services),
                      "valid": not errors, "errors": errors}
        else:
            if errors:
                records = []
                for service in services:
                    cls = service.get("policy")
                    status = ("EXCLUDED" if cls == "NO_TOUCH" else
                              "MANUAL_REVIEW" if cls == "MANUAL" else "BLOCKED")
                    problems = service_errors.get(service["name"], [])
                    if status == "BLOCKED":
                        problems = [*problems, "policy invalid: runtime inspection skipped"]
                    records.append({
                        "name": service["name"],
                        "policy": cls,
                        "ownership": service.get("ownership"),
                        "classification": status,
                        "issues": problems,
                        "runtime": {"status": "NOT_CHECKED"},
                        "release_management": public_release_management(service),
                        "proposed_target": None,
                    })
            else:
                records = [assessment(s, docker_snapshot(s) if args.live else evidence.get(s["name"]))
                           for s in services]
            result = {"operation": args.operation, "read_only": True,
                      "policy_valid": not errors, "errors": errors,
                      "services": records,
                      "note": "CANDIDATE/GATED is not approval. No Docker mutation is implemented."}
        if args.format == "json":
            print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        else:
            if errors:
                for error in errors:
                    print(f"ERROR: {error}")
            if args.operation == "validate":
                print(f"Policy: {'PASS' if result['valid'] else 'FAIL'} "
                      f"({len(services)} services)")
            else:
                for record in result["services"]:
                    print(f"{record['name']}: {record['classification']} "
                          f"[{record['policy']}]")
                    for issue in record["issues"]:
                        print(f"  - {issue}")
                print("READ-ONLY. No changes made.")
        return 2 if errors or (args.operation == "validate" and not result["valid"]) else 0
    except (PolicyError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
