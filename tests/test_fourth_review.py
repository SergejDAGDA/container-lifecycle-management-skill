"""Fourth independent review: safety boundaries for malformed policy and output.

These use only synthetic YAML and mocked Docker; never a real container.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from copy import deepcopy
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "container-lifecycle-management" / "scripts"))
import maintenance
import native_policy
from native_runtime import parse_targeted_inspect


class FourthReviewTest(unittest.TestCase):
    def native(self):
        return maintenance.load_policy(ROOT / "examples/native-policy.yaml")

    def portable(self):
        return maintenance.load_policy(ROOT / "examples/services.yaml")

    def cli(self, data, *, operation="plan", live=False):
        with tempfile.TemporaryDirectory() as td:
            filepath = Path(td) / "services.yaml"
            filepath.write_text(yaml.safe_dump(data), encoding="utf-8")
            out = io.StringIO()
            with patch("maintenance.docker_snapshot", side_effect=AssertionError("Docker touched")), \
                 patch("native_policy._runtime", side_effect=AssertionError("Docker touched")), \
                 contextlib.redirect_stdout(out):
                rc = maintenance.main(["--policy", str(filepath), "--format", "json"] +
                                      (["--live"] if live else []) + [operation])
            return rc, json.loads(out.getvalue())

    def test_portable_unhashable_policy_fails_closed_without_docker(self):
        for bad in ([], {}, ["MANUAL"], {"policy": "AUTO_SAFE"}):
            with self.subTest(bad=bad):
                p = self.portable()
                p["services"][0]["policy"] = bad
                for operation in ("plan", "audit", "status"):
                    rc, result = self.cli(p, operation=operation, live=True)
                    self.assertEqual(rc, 2)
                    self.assertFalse(result["policy_valid"])
                    self.assertEqual(len(result["services"]), 3)
                    self.assertEqual(result["services"][0]["classification"], "BLOCKED")

    def test_portable_named_mapping_with_nonstring_nested_key_fails(self):
        p = {"schema_version": "1",
             "services": {"demo-web": {1: "invalid", "policy": "AUTO_SAFE",
                                        "ownership": "sandbox"}}}
        rc, result = self.cli(p, live=True)
        self.assertEqual(rc, 2)
        self.assertEqual(len(result["services"]), 1)
        self.assertTrue(any("keys must all be strings" in error for error in result["errors"]))

    def test_wrong_schema_version_type_fails_closed(self):
        p = self.portable()
        p["schema_version"] = 1
        rc, report = self.cli(p)
        self.assertEqual(rc, 2)
        self.assertFalse(report["policy_valid"])

    def test_unknown_group_and_unhashable_update_group_fail(self):
        for bad in (["synthetic-web-stack"], {"name": "synthetic-web-stack"}, "missing-group"):
            with self.subTest(bad=bad):
                p = self.native()
                p["services"][0]["dependencies"]["update_group"] = bad
                services, errors, _ = native_policy.structure(p)
                self.assertTrue(any("update_group" in err for err in errors), errors)
                rc, report = self.cli(p, live=True)
                self.assertEqual(rc, 2)
                self.assertEqual(len(report["services"]), 3)
                self.assertEqual(report["services"][0]["runtime"]["status"], "NOT_CHECKED")

    def test_exact_member_wrong_update_group_fails(self):
        p = self.native()
        p["services"][0]["dependencies"].pop("update_group")
        _, errors, _ = native_policy.structure(p)
        self.assertTrue(any("belongs to another group" in err for err in errors), errors)

    def test_malformed_compose_project_rejected(self):
        for bad in (None, [], {}, 3, True):
            with self.subTest(bad=bad):
                p = self.native()
                p["services"][0]["identity"]["compose_project"] = bad
                _, errors, _ = native_policy.structure(p)
                self.assertTrue(any("compose_project" in err for err in errors), errors)

    def test_arbitrary_release_extension_never_echoes_secret(self):
        sentinel = "SYNTHETIC_RELEASE_SECRET_DO_NOT_ECHO"
        for native in (True, False):
            for operation in ("plan", "status", "audit"):
                with self.subTest(native=native, operation=operation):
                    p = self.native() if native else self.portable()
                    record = p["services"][0]
                    record["release_management"] = {
                        "strategy": "upstream_managed", "release_authority": "upstream_project",
                        "version_monitoring": False, "automatic_updates": False,
                        "token": sentinel,
                    }
                    rc, report = self.cli(p, operation=operation, live=True)
                    self.assertEqual(rc, 2)
                    self.assertNotIn(sentinel, json.dumps(report))
                    self.assertTrue(any("unsupported fields" in e for e in report["errors"]))

    def test_public_release_projection_cannot_echo_unknown_fields(self):
        from release_management import public_release_management
        sentinel = "SECRET_TOKEN_NOT_TO_BE_DISPLAYED"
        self.assertNotIn(sentinel, str(public_release_management({
            "release_management": {
                "strategy": "upstream_managed",
                "release_authority": "upstream_project",
                "version_monitoring": True,
                "automatic_updates": False,
                "some_other_field": sentinel,
            }
        })))

    def test_nonstring_native_inspect_stdout_yields_unverified(self):
        p = self.native()
        service = p["services"][0]
        for stdout in (None, [], {}, 123):
            with self.subTest(stdout=stdout):
                first = SimpleNamespace(returncode=0, stdout="synthetic-id\n")
                second = SimpleNamespace(returncode=0, stdout=stdout)
                with patch("native_policy.subprocess.run", side_effect=[first, second]):
                    result = native_policy._runtime(service)
                self.assertEqual(result["status"], "UNVERIFIED")

    def test_targeted_inspect_rejects_nontext(self):
        for item in (None, [], {}, 123):
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    parse_targeted_inspect(item)

    def test_native_existing_valid_fixture_remains_valid(self):
        p = self.native()
        _, errors, warnings = native_policy.structure(p)
        self.assertFalse(errors, errors)
        self.assertFalse(warnings, warnings)

    def test_public_safety_contract_must_not_implicitly_ignore_new_global_rules(self):
        p = self.native()
        p["safety_invariants"]["unknown_global_rule"] = "unverified"
        _, errors, _ = native_policy.structure(p)
        self.assertTrue(any("unsupported global safety invariant" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
