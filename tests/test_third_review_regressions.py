"""Adversarial regression tests for the third independent Codex review.

No Docker/SSH/server or mutating operations. All Docker output is synthetic.
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "container-lifecycle-management" / "scripts"))

import maintenance
import native_policy
import yaml


class ThirdReviewTest(unittest.TestCase):
    def native(self):
        return maintenance.load_policy(ROOT / "examples" / "native-policy.yaml")

    def portable(self):
        return maintenance.load_policy(ROOT / "examples" / "services.yaml")

    def test_group_member_identity_wrong_type_does_not_crash(self):
        for bad in ([], "broken", None, {"compose_services": "web"}):
            with self.subTest(bad=bad):
                policy = self.native()
                policy["services"][0]["identity"] = bad
                services, errors, _ = native_policy.structure(policy)
                self.assertEqual(len(services), 3)
                self.assertTrue(errors)
                self.assertTrue(any("identity" in e for e in errors), errors)

    def test_alias_owner_dependencies_wrong_type_does_not_crash(self):
        for bad in ([], "broken", None):
            with self.subTest(bad=bad):
                policy = self.native()
                policy["services"][1]["dependencies"] = bad
                services, errors, _ = native_policy.structure(policy)
                self.assertEqual(len(services), 3)
                self.assertTrue(any("dependencies" in e for e in errors), errors)

    def test_alias_owner_identity_wrong_type_does_not_crash(self):
        for bad in ([], "broken", None):
            with self.subTest(bad=bad):
                policy = self.native()
                policy["services"][1]["identity"] = bad
                _, errors, _ = native_policy.structure(policy)
                self.assertTrue(any("identity" in e for e in errors), errors)

    def test_bad_native_policy_keeps_inventory_and_never_contacts_docker(self):
        policy = self.native()
        policy["services"][1]["identity"] = "invalid"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "native-policy.yaml"
            path.write_text(yaml.safe_dump(policy), encoding="utf-8")
            output = io.StringIO()
            with patch("native_policy._runtime", side_effect=AssertionError("Docker accessed")):
                with contextlib.redirect_stdout(output):
                    rc = maintenance.main(
                        ["--policy", str(path), "--live", "--format", "json", "audit"])
            self.assertEqual(rc, 2)
            data = json.loads(output.getvalue())
            self.assertEqual(len(data["services"]), 3)
            self.assertTrue(all(s["runtime"]["status"] == "NOT_CHECKED"
                                for s in data["services"]))

    def test_malformed_optional_release_management_never_crashes(self):
        for field in ("strategy", "release_authority"):
            for value in (["wrong"], {"unexpected": True}, 3, False):
                with self.subTest(field=field, value=value):
                    native = self.native()
                    native["services"][0]["release_management"] = {
                        "strategy": "project_managed",
                        "release_authority": "application_project",
                        "version_monitoring": False,
                        "automatic_updates": False,
                    }
                    native["services"][0]["release_management"][field] = value
                    _, errors, _ = native_policy.structure(native)
                    self.assertTrue(any("release_management" in e for e in errors), errors)
                    portable = self.portable()
                    portable["services"][0]["release_management"] = {
                        "strategy": "project_managed",
                        "release_authority": "application_project",
                        "version_monitoring": False,
                        "automatic_updates": False,
                    }
                    portable["services"][0]["release_management"][field] = value
                    _, errors = maintenance.normalize(portable)
                    self.assertTrue(any("release_management" in e for e in errors), errors)

    def test_unknown_global_security_invariant_fails_structural_validation(self):
        for value in (True, False, "yes", {"enabled": True}):
            with self.subTest(value=value):
                policy = self.native()
                policy["safety_invariants"]["allow_privileged"] = value
                _, errors, _ = native_policy.structure(policy)
                self.assertTrue(any("unsupported global safety invariant" in e
                                    for e in errors), errors)

    def test_unknown_global_security_invariant_fails_cli_validate(self):
        policy = self.native()
        policy["safety_invariants"]["allow_privileged"] = True
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "native-policy.yaml"
            path.write_text(yaml.safe_dump(policy), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(maintenance.main(["--policy", str(path), "validate"]), 2)

    def test_valid_global_invariants_unchanged(self):
        policy = self.native()
        _, errors, _ = native_policy.structure(policy)
        self.assertEqual(errors, [])

    def test_portable_inspect_malformed_metadata_fails_closed(self):
        base = {
            "Id": "synthetic-container",
            "Image": "sha256:" + "a" * 64,
            "Config": {"Image": "example.invalid/app:1"},
            "State": {"Running": True, "Health": {"Status": "healthy"}},
            "Mounts": [{"Type": "bind", "Source": "/synthetic/state",
                        "Destination": "/data", "RW": True}],
        }
        malformed = (
            [],
            None,
            {"State": [], "Config": {"Image": "example.invalid/app:1"}},
            {"State": {"Running": True}, "Config": []},
            dict(base, Mounts=["wrong-type"]),
            dict(base, Mounts=None),
            dict(base, State={"Running": "true"}),
            dict(base, State={"Running": True, "Health": "healthy"}),
            dict(base, Mounts=[{"Type": "bind", "Source": "/state",
                                "Destination": "/data", "RW": "true"}]),
        )
        service = self.portable()["services"][0]
        for idx, value in enumerate(malformed):
            with self.subTest(input=idx):
                response1 = SimpleNamespace(returncode=0, stdout="container-id\n")
                response2 = SimpleNamespace(returncode=0, stdout=json.dumps(value))
                with patch("maintenance.subprocess.run",
                           side_effect=(response1, response2)) as runner:
                    result = maintenance.docker_snapshot(service)
                self.assertEqual(result["status"], "unverified")
                self.assertEqual(runner.call_count, 2)

    def test_portable_inspect_valid_metadata_works(self):
        record = {
            "Id": "synthetic-container", "Image": "sha256:" + "b" * 64,
            "Config": {"Image": "example.invalid/app:1"},
            "State": {"Running": True},
            "Mounts": []
        }
        response1 = SimpleNamespace(returncode=0, stdout="container-id\n")
        response2 = SimpleNamespace(returncode=0, stdout=json.dumps(record))
        with patch("maintenance.subprocess.run",
                   side_effect=(response1, response2)):
            result = maintenance.docker_snapshot(self.portable()["services"][0])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["health"], "none")
        self.assertEqual(result["mounts"], [])


if __name__ == "__main__":
    unittest.main()
