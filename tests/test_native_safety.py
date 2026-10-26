"""Adversarial native policy and Docker metadata parity tests.

No Docker daemon, SSH, or mutating operation is invoked.
"""
from copy import deepcopy
from pathlib import Path
import json
import contextlib
import io
import sys
import tempfile
from unittest import mock
import yaml
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "container-lifecycle-management" / "scripts"))
import maintenance
from native_policy import structure, assess_native
from native_safety import safety_issues
from native_runtime import contract_differences, parse_targeted_inspect


class NativeSemanticAndRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = maintenance.load_policy(ROOT / "examples" / "native-policy.yaml")

    def policy(self):
        return deepcopy(self.example)

    def test_complete_contract_succeeds_only_with_explicit_gates(self):
        s = self.policy()["services"][0]
        self.assertFalse(safety_issues(s), safety_issues(s))

    def test_unknown_database_fails_closed(self):
        data = self.policy()
        data["services"][0]["state_contract"]["databases"] = "unknown"
        _, errors, _ = structure(data)
        self.assertTrue(any("databases" in x for x in errors), errors)
        result = assess_native(data, data["services"])
        self.assertEqual(result[0]["classification"], "BLOCKED")

    def test_invalid_native_policy_keeps_inventory_and_never_inspects_docker(self):
        policy = self.policy()
        policy["services"][0]["state_contract"]["databases"] = "unknown"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "policy.yaml"
            path.write_text(yaml.safe_dump(policy), encoding="utf-8")
            output = io.StringIO()
            with mock.patch("native_policy._runtime", side_effect=AssertionError(
                    "must not access Docker with invalid policy")):
                with contextlib.redirect_stdout(output):
                    rc = maintenance.main([
                        "--policy", str(path), "--live", "--format", "json", "audit"
                    ])
            self.assertEqual(rc, 2)
            result = json.loads(output.getvalue())
            self.assertEqual(len(result["services"]), 3)
            self.assertFalse(result["policy_valid"])
            self.assertEqual(result["services"][0]["classification"], "BLOCKED")
            self.assertEqual(result["services"][0]["runtime"]["status"], "NOT_CHECKED")
            self.assertEqual(result["services"][1]["classification"], "MANUAL_REVIEW")
            self.assertEqual(result["services"][2]["classification"], "EXCLUDED")

    def test_unknown_state_even_when_complete_fails(self):
        data = self.policy()
        for field in ("uploaded_user_files", "account_state", "instance_identity", "disposable_caches"):
            with self.subTest(field=field):
                mutated = deepcopy(data)
                mutated["services"][0]["state_contract"][field] = "unknown"
                self.assertTrue(safety_issues(mutated["services"][0]))

    def test_truthy_string_is_not_reproducibility_proof(self):
        s = self.policy()["services"][0]
        s["deployment"]["source_reproducible"] = "true"
        self.assertTrue(any("source_reproducible" in x for x in safety_issues(s)))

    def test_empty_rollback_migration_topology_smoke_fails(self):
        for section in ("rollback", "migration", "topology", "health", "smoke"):
            with self.subTest(section=section):
                s = self.policy()["services"][0]
                s[section] = {}
                self.assertTrue(safety_issues(s))

    def test_unsafe_auto_safe_rollback_is_rejected(self):
        s = self.policy()["services"][0]
        s["migration"]["possible"] = True
        s["rollback"]["state_rollback_may_be_required"] = True
        self.assertTrue(any("AUTO_SAFE" in x for x in safety_issues(s)))

    def test_nonboolean_backup_and_topology_gates(self):
        for section, key in (("backup", "required"), ("topology", "mounts_invariant")):
            s = self.policy()["services"][0]
            s[section][key] = 1
            self.assertTrue(any(section + "." + key in x for x in safety_issues(s)))

    def test_undocumented_mount_mode_fails(self):
        s = self.policy()["services"][0]
        s["state_contract"]["binds"] = [{
            "source": "/synthetic-data", "target": "/data", "mode": "maybe"
        }]
        self.assertTrue(any("mode" in x for x in safety_issues(s)))

    def snapshot(self):
        s = self.policy()["services"][0]
        return s, [{
            "service": "web",
            "image_id": s["image"]["immutable_identity"],
            "configured_image": s["image"]["runtime_reference"],
            "running": True, "health": "healthy", "restart_count": 0,
            "mounts": [], "ports": {}, "networks": {"synthetic_net": {}},
            "privileged": False, "readonly_root": False,
            "cap_add": [], "cap_drop": [], "security_opt": [],
            "user": "", "network_mode": "synthetic_net"
        }]

    def test_exact_synthetic_runtime_is_metadata_only(self):
        service, snapshots = self.snapshot()
        self.assertEqual(contract_differences(service, snapshots), [])

    def test_wrong_image_is_drift(self):
        s, snaps = self.snapshot()
        snaps[0]["image_id"] = "sha256:" + "b" * 64
        self.assertTrue(any("image identity" in x for x in contract_differences(s, snaps)))

    def test_wrong_port_is_drift(self):
        s, snaps = self.snapshot()
        snaps[0]["ports"] = {"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8079"}]}
        self.assertTrue(any("port" in x for x in contract_differences(s, snaps)))

    def test_wrong_network_is_drift(self):
        s, snaps = self.snapshot()
        snaps[0]["networks"] = {"unexpected_net": {}}
        self.assertTrue(any("network" in x for x in contract_differences(s, snaps)))

    def test_unexpected_mount_is_drift(self):
        s, snaps = self.snapshot()
        snaps[0]["mounts"] = [{
            "Type": "volume", "Name": "other_volume", "Destination": "/data", "RW": True
        }]
        self.assertTrue(any("mount" in x for x in contract_differences(s, snaps)))

    def test_mount_identity_and_mode_must_match(self):
        s, snaps = self.snapshot()
        s["state_contract"]["binds"] = [{
            "source": "/host/data", "target": "/data", "mode": "ro"
        }]
        snaps[0]["mounts"] = [{
            "Type": "bind", "Source": "/host/data", "Destination": "/data", "RW": True
        }]
        self.assertTrue(any("mount identity/mode" in x for x in contract_differences(s, snaps)))

    def test_privileged_runtime_is_drift(self):
        s, snaps = self.snapshot()
        snaps[0]["privileged"] = True
        self.assertTrue(any("privileged" in x for x in contract_differences(s, snaps)))

    def test_no_touch_is_not_inspected_even_when_live(self):
        data = self.policy()
        protected = data["services"][2]
        r = assess_native(data, [protected], live=True)
        self.assertEqual(r[0]["runtime"]["status"], "NOT_CHECKED")

    def test_targeted_inspect_parser_rejects_incomplete_data(self):
        with self.assertRaises(ValueError):
            parse_targeted_inspect(json.dumps({"Env": ["TOP_SECRET=hidden"]}))
        self.assertNotIn("Env", str(self.snapshot()[1]))


if __name__ == "__main__":
    unittest.main()
