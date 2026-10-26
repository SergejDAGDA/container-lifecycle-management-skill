"""PR22 audit remediations: synthetic policy/runtime inputs and mocked Docker only.

No host, real Docker daemon, production policy, secrets or mutation commands.
"""
from __future__ import annotations

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

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "container-lifecycle-management" / "scripts"))
import maintenance  # noqa: E402
import native_policy  # noqa: E402

CANARY = "SECRET_CANARY_DO_NOT_LEAK"


class Audit22HardeningTests(unittest.TestCase):
    def portable(self):
        return maintenance.load_policy(ROOT / "examples/services.yaml")

    def native(self):
        return maintenance.load_policy(ROOT / "examples/native-policy.yaml")

    def call(self, policy, *options, runtime=None):
        with tempfile.TemporaryDirectory(prefix="msc-audit22-only-") as root:
            filepath = Path(root) / "policy.yaml"
            filepath.write_text(yaml.safe_dump(policy), encoding="utf-8")
            args = ["--policy", str(filepath), "--format", "json", *options]
            if runtime is not None:
                evidence = Path(root) / "runtime.json"
                evidence.write_text(json.dumps(runtime), encoding="utf-8")
                args[4:4] = ["--runtime-json", str(evidence)]
            out = io.StringIO()
            err = io.StringIO()
            with patch("maintenance.docker_snapshot",
                       side_effect=AssertionError("Docker cannot be consulted")), \
                 patch("native_policy._runtime",
                       side_effect=AssertionError("Docker cannot be consulted")), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = maintenance.main(args)
            return code, out.getvalue(), err.getvalue()

    def test_all_existing_portable_fixtures_remain_valid(self):
        for name in ("services.yaml", "project-managed.yaml",
                     "repository-managed.yaml"):
            with self.subTest(fixture=name):
                policy = maintenance.load_policy(ROOT / "examples" / name)
                _, errors = maintenance.normalize(policy)
                self.assertEqual(errors, [])

    def test_unknown_global_portable_rules_fail_closed_without_echoing_values(self):
        policy = self.portable()
        policy["safety_invariants"] = {"allow_unsafe_operations": CANARY}
        _, errors = maintenance.normalize(policy)
        self.assertTrue(any("unsupported portable top-level" in e for e in errors))
        for mode in ("validate", "plan", "audit", "status"):
            code, out, err = self.call(policy, "--live", mode)
            self.assertEqual(code, 2)
            self.assertNotIn(CANARY, out + err)
            self.assertNotIn("Traceback", out + err)
            if mode != "validate":
                result = json.loads(out)
                self.assertFalse(result["policy_valid"])
                self.assertEqual(result["services"][0]["runtime"]["status"],
                                 "NOT_CHECKED")

    def test_unknown_service_rules_are_not_implicitly_enforced(self):
        policy = self.portable()
        policy["services"][0]["approval_override"] = {"token": CANARY}
        _, errors = maintenance.normalize(policy)
        self.assertIn("unsupported portable service fields", " ".join(errors))
        code, out, err = self.call(policy, "--live", "plan")
        self.assertEqual(code, 2)
        self.assertNotIn(CANARY, out + err)

    def test_unknown_nested_safety_rules_refused(self):
        for section in ("deployment", "image", "state", "backup",
                        "rollback", "health", "smoke", "target"):
            with self.subTest(section=section):
                policy = self.portable()
                policy["services"][0][section]["critical_override"] = CANARY
                _, errors = maintenance.normalize(policy)
                self.assertTrue(any("unsupported " + section + " fields" in e
                                    for e in errors), errors)
                self.assertNotIn(CANARY, " ".join(errors))

    def test_unknown_fields_on_minimal_manual_record_refused(self):
        policy = self.portable()
        policy["services"][1]["manual_override"] = CANARY
        _, errors = maintenance.normalize(policy)
        self.assertTrue(any("unsupported portable service fields" in e
                            for e in errors))

    def test_extension_manifest_in_portable_policy_requires_explicit_mapping(self):
        policy = self.portable()
        policy["safety_adapter"] = {
            "api": "maintain-server-containers/safety-adapter/v1",
            "id": "claimed-but-not-reviewed",
            "token": CANARY,
        }
        _, errors = maintenance.normalize(policy)
        self.assertTrue(errors)
        self.assertNotIn(CANARY, " ".join(errors))

    def test_native_revision_true_is_rejected_without_live_contact(self):
        for revision in (True, False, 1.0, "1", None):
            with self.subTest(revision=revision):
                policy = self.native()
                policy["policy_revision"] = revision
                _, errors, _ = native_policy.structure(policy)
                self.assertTrue(any("revision" in e for e in errors))
                code, out, err = self.call(policy, "--live", "plan")
                self.assertEqual(code, 2)
                self.assertNotIn("Traceback", out + err)
                self.assertEqual(json.loads(out)["services"][0]["runtime"]["status"],
                                 "NOT_CHECKED")

    def test_portable_synthetic_runtime_nonmapping_rejected(self):
        policy = self.portable()
        for bad in (["fake"], CANARY, None, True, 15):
            with self.subTest(bad=bad):
                code, out, err = self.call(
                    policy, "plan", runtime={"demo-web": bad})
                self.assertEqual(code, 2)
                self.assertNotIn("Traceback", out + err)
                self.assertNotIn(CANARY, out + err)
                self.assertIn("runtime evidence", err.lower())

    def test_unexpected_extra_runtime_record_must_not_hide_wrong_type(self):
        code, out, err = self.call(
            self.portable(), "status",
            runtime={"demo-web": {"status": "verified"},
                     "other-service": CANARY})
        self.assertEqual(code, 2)
        self.assertNotIn(CANARY, out + err)

    def test_assessment_direct_invalid_runtime_is_blocked_and_redacted(self):
        service = self.portable()["services"][0]
        for bad in (CANARY, [], True, 1):
            with self.subTest(bad=bad):
                report = maintenance.assessment(service, bad)
                self.assertEqual(report["classification"], "BLOCKED")
                self.assertEqual(report["runtime"]["status"], "unverified")
                self.assertIn("runtime evidence format invalid", report["issues"])
                self.assertNotIn(CANARY, repr(report))

    def test_portable_docker_template_is_only_a_fixed_small_projection(self):
        template = maintenance.PORTABLE_INSPECT_TEMPLATE
        for needed in (".Id", ".Image", ".Config.Image", ".State.Running",
                       ".State.Health", ".Mounts", "$mount.Type", "$mount.RW"):
            self.assertIn(needed, template)
        for forbidden in ("json .}}", ".Config.Env", ".Config.Labels",
                          ".HostConfig", ".Args", ".NetworkSettings"):
            self.assertNotIn(forbidden, template)
        self.assertLess(len(template), 1200)

    def test_portable_docker_runner_receives_restricted_template(self):
        first = SimpleNamespace(returncode=0, stdout="synthetic123\n")
        second = SimpleNamespace(returncode=0, stdout=json.dumps({
            "Id": "synthetic-container-id",
            "Image": "sha256:" + "a" * 64,
            "Config": {"Image": "example.invalid/demo-web:1.2.3"},
            "State": {"Running": True, "Health": None},
            "Mounts": [],
        }))
        with patch("maintenance.subprocess.run", side_effect=[first, second]) as run:
            result = maintenance.docker_snapshot(self.portable()["services"][0])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["health"], "none")
        self.assertEqual(run.call_count, 2)
        command = run.call_args_list[1].args[0]
        self.assertEqual(command[0:3], ["docker", "inspect", "--format"])
        self.assertEqual(command[3], maintenance.PORTABLE_INSPECT_TEMPLATE)
        self.assertNotIn("{{json .}}", command)

    def test_bad_inspect_payload_is_still_unverified(self):
        first = SimpleNamespace(returncode=0, stdout="synthetic123\n")
        second = SimpleNamespace(returncode=0, stdout=json.dumps({
            "Image": "sha256:" + "a" * 64, "State": {"Running": True},
            "Config": {"Image": "example.invalid/demo-web:1.2.3"},
            "Mounts": [{"Type": "bind", "Source": CANARY,
                        "Destination": "/target", "RW": "not-a-boolean"}],
        }))
        with patch("maintenance.subprocess.run", side_effect=[first, second]):
            result = maintenance.docker_snapshot(self.portable()["services"][0])
        self.assertEqual(result["status"], "unverified")
        self.assertNotIn(CANARY, repr(result))


if __name__ == "__main__":
    unittest.main()
