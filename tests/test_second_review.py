"""Regression tests for all findings of the second independent Codex review.

Synthetic only: no Docker, SSH or deployment commands.
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "container-lifecycle-management" / "scripts"))
import maintenance
import native_policy
from native_safety import safety_issues
from native_runtime import parse_targeted_inspect, contract_differences
import yaml


class SecondReviewRegressionTest(unittest.TestCase):
    def native_policy(self):
        return maintenance.load_policy(ROOT / "examples/native-policy.yaml")

    def portable_policy(self):
        return maintenance.load_policy(ROOT / "examples/services.yaml")

    def test_empty_evidence_is_rejected_not_satisfied_by_all_empty(self):
        fields = (
            ("backup", "recovery_mechanism"),
            ("backup", "freshness_requirement"),
            ("backup", "restore_verification_requirement"),
            ("migration", "rollback_class"),
            ("rollback", "previous_image"),
            ("rollback", "previous_image_identity"),
            ("rollback", "deployment_source"),
            ("topology", "container_identity"),
            ("smoke", "profile"),
            ("state_contract", "instance_identity"),
        )
        for section, field in fields:
            with self.subTest(field=f"{section}.{field}"):
                policy = self.native_policy()
                item = policy["services"][0]
                item[section][field] = []
                issues = safety_issues(item)
                self.assertTrue(any(f"{section}.{field}" in issue for issue in issues), issues)
                _, errs, _ = native_policy.structure(policy)
                self.assertTrue(any(f"{section}.{field}" in err for err in errs), errs)

    def test_explicit_empty_state_lists_are_valid(self):
        s = self.native_policy()["services"][0]
        for field in ("binds", "named_volumes", "databases", "secrets", "disposable_caches"):
            s["state_contract"][field] = []
        self.assertFalse(safety_issues(s), safety_issues(s))

    def test_unknown_invariant_blocked_by_validate(self):
        p = self.native_policy()
        p["services"][0]["topology"]["security_invariants"] = ["allow_privileged"]
        _, errs, _ = native_policy.structure(p)
        self.assertTrue(any("unsupported invariant (value withheld)" in err for err in errs), errs)
        self.assertFalse(any("allow_privileged" in err for err in errs), errs)

    def test_valid_special_user_invariant_allowed(self):
        p = self.native_policy()
        p["services"][0]["topology"]["security_invariants"] = ["user_1000_1000"]
        _, errs, _ = native_policy.structure(p)
        self.assertFalse(errs, errs)

    def test_portable_invalid_policy_never_calls_docker_even_live(self):
        p = self.portable_policy()
        p["services"][0]["deployment"] = "not-a-mapping"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "policy.yaml"
            path.write_text(yaml.safe_dump(p), encoding="utf-8")
            output = io.StringIO()
            with patch("maintenance.docker_snapshot",
                       side_effect=AssertionError("Docker called on malformed policy")):
                with contextlib.redirect_stdout(output):
                    rc = maintenance.main([
                        "--policy", str(path), "--live", "--format", "json", "audit"
                    ])
            result = json.loads(output.getvalue())
            self.assertEqual(rc, 2)
            self.assertFalse(result["policy_valid"])
            self.assertEqual(len(result["services"]), 3)
            self.assertEqual(result["services"][0]["classification"], "BLOCKED")
            self.assertEqual(result["services"][0]["runtime"]["status"], "NOT_CHECKED")
            self.assertEqual(result["services"][1]["classification"], "MANUAL_REVIEW")
            self.assertEqual(result["services"][2]["classification"], "EXCLUDED")

    def test_missing_portable_state_policy_also_skips_docker(self):
        p = self.portable_policy()
        p["services"][0]["state"]["complete"] = False
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "policy.yaml"
            path.write_text(yaml.safe_dump(p), encoding="utf-8")
            with patch("maintenance.docker_snapshot",
                       side_effect=AssertionError("Docker called on unsafe state")):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(maintenance.main(
                        ["--policy", str(path), "--live", "audit"]), 2)

    def test_malformed_portable_rollback_returns_blocker(self):
        p = self.portable_policy()
        p["services"][0]["rollback"] = "invalid"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "policy.yaml"
            path.write_text(yaml.safe_dump(p), encoding="utf-8")
            with patch("maintenance.docker_snapshot", side_effect=AssertionError("Docker")):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(maintenance.main(
                        ["--policy", str(path), "--live", "audit"]), 2)

    def snapshot(self):
        service = deepcopy(self.native_policy()["services"][0])
        snap = {
            "service": "web", "image_id": service["image"]["immutable_identity"],
            "configured_image": service["image"]["runtime_reference"],
            "running": True, "health": "healthy", "restart_count": 0,
            "mounts": [], "ports": {}, "networks": {"synthetic_net": {}},
            "privileged": False, "readonly_root": False,
            "cap_add": [], "cap_drop": [], "security_opt": [],
            "user": "", "network_mode": "synthetic_net"
        }
        return service, snap

    def test_host_networking_drift_without_named_networks(self):
        service, snap = self.snapshot()
        service["topology"]["networks"] = []
        snap["networks"] = {}
        snap["network_mode"] = "host"
        issues = contract_differences(service, [snap])
        self.assertTrue(any("network_mode" in issue for issue in issues), issues)

    def test_docker_socket_requires_exact_bind_source_and_ro_mode(self):
        service, snap = self.snapshot()
        service["topology"]["security_invariants"] = ["read_only_docker_socket"]
        service["state_contract"]["binds"] = [{
            "source": "/other/socket", "target": "/var/run/docker.sock", "mode": "ro"
        }]
        snap["mounts"] = [{
            "Type": "bind", "Source": "/other/socket",
            "Destination": "/var/run/docker.sock", "RW": False
        }]
        issues = contract_differences(service, [snap])
        self.assertTrue(any("docker socket" in issue for issue in issues), issues)

    def test_correct_ro_socket_bind_satisfies_specific_invariant(self):
        service, snap = self.snapshot()
        service["topology"]["security_invariants"] = ["read_only_docker_socket"]
        service["state_contract"]["binds"] = [{
            "source": "/var/run/docker.sock", "target": "/var/run/docker.sock", "mode": "ro"
        }]
        snap["mounts"] = [{
            "Type": "bind", "Source": "/var/run/docker.sock",
            "Destination": "/var/run/docker.sock", "RW": False
        }]
        issues = contract_differences(service, [snap])
        self.assertFalse(issues, issues)

    def raw_inspect_values(self):
        _, s = self.snapshot()
        return [
            s["image_id"], s["configured_image"], s["running"], s["health"],
            s["restart_count"], s["mounts"], s["ports"], s["networks"],
            s["privileged"], s["readonly_root"], s["cap_add"], s["cap_drop"],
            s["security_opt"], s["user"], s["network_mode"]
        ]

    def test_inspect_template_projection_accepts_valid_types(self):
        values = self.raw_inspect_values()
        self.assertEqual(parse_targeted_inspect("\n".join(map(json.dumps, values)))["image_id"],
                         values[0])

    def test_inspect_projection_rejects_malformed_runtime_types(self):
        for index, value in ((2, "true"), (4, False), (5, "[]"),
                             (8, "true"), (11, "ALL"), (14, []),
                             (6, {"80/tcp": "something"})):
            with self.subTest(index=index):
                values = self.raw_inspect_values()
                values[index] = value
                with self.assertRaises(ValueError):
                    parse_targeted_inspect("\n".join(map(json.dumps, values)))


if __name__ == "__main__":
    unittest.main()
