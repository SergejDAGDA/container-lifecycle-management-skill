"""Synthetic adapter conformance and adapter-boundary regressions.

No dynamic loading, Docker, SSH, deployment or project-specific dependencies.
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
from safety_adapter import (API, TrustedSafetyAdapter, validate_adapter_service)


ID = "synthetic.project-safety"
DIGEST = "sha256:" + "b" * 64
EXTRA = "synthetic_extra_gate"
MANIFEST = {"api": API, "id": ID, "version": "1.0.0",
            "digest": DIGEST, "required": True}


class SafetyAdapterTest(unittest.TestCase):
    def policy(self):
        data = maintenance.load_policy(ROOT / "examples/native-policy.yaml")
        data["safety_invariants"][EXTRA] = "must_validate"
        data["safety_adapter"] = deepcopy(MANIFEST)
        return data

    def trusted(self, status="PASS", claims=None, check=None, digest=DIGEST):
        return TrustedSafetyAdapter(ID, "1.0.0", digest,
                                    frozenset({EXTRA} if claims is None else claims),
                                    check if check is not None else
                                    lambda p: {EXTRA: status})

    def errors(self, p, registry=None):
        _, errors, _ = native_policy.structure(p, trusted_adapters=registry)
        return errors

    def test_missing_adapter_is_not_accepted(self):
        issues = self.errors(self.policy())
        self.assertTrue(any("not registered" in x for x in issues), issues)

    def test_undeclared_adapter_does_not_claim_global_rule(self):
        p = self.policy()
        p.pop("safety_adapter")
        issues = self.errors(p)
        self.assertTrue(any("unsupported global safety invariant" in x for x in issues), issues)

    def test_explicitly_registered_claimed_rule_can_pass(self):
        self.assertEqual(self.errors(self.policy(), {ID: self.trusted()}), [])

    def test_missing_claim_is_error(self):
        issues = self.errors(self.policy(), {ID: self.trusted(claims=set())})
        self.assertTrue(any("claim coverage mismatch" in x for x in issues), issues)

    def test_extra_claim_is_error(self):
        issues = self.errors(self.policy(), {ID: self.trusted(claims={EXTRA, "other"})})
        self.assertTrue(any("claim coverage mismatch" in x for x in issues), issues)

    def test_registered_adapter_pin_mismatch_is_error(self):
        issues = self.errors(self.policy(), {ID: self.trusted(digest="sha256:" + "c" * 64)})
        self.assertTrue(any("mismatch" in x for x in issues), issues)

    def test_invalid_manifest_must_not_exec_or_download(self):
        for key in ("api", "id", "version", "digest", "required"):
            p = self.policy()
            p["safety_adapter"][key] = "../unsafe.py" if key != "required" else False
            self.assertTrue(self.errors(p, {ID: self.trusted()}), key)
        p = self.policy()
        p["safety_adapter"]["python_import"] = "os.system"
        issues = self.errors(p, {ID: self.trusted()})
        self.assertTrue(any("manifest fields" in x for x in issues), issues)

    def test_unclaimed_rule_still_fails_when_other_rule_claimed(self):
        p = self.policy()
        p["safety_invariants"]["another_rule"] = "enforced"
        issues = self.errors(p, {ID: self.trusted()})
        self.assertTrue(any("claim coverage mismatch" in x for x in issues), issues)

    def test_nonpassing_statuses_never_approve(self):
        for status in ("UNRESOLVED", "BLOCK", "ERROR", None, ["PASS"]):
            with self.subTest(status=status):
                issues = self.errors(self.policy(), {ID: self.trusted(status=status)})
                self.assertTrue(issues, status)

    def test_adapter_exceptions_never_leak_values(self):
        sentinel = "VERY_PRIVATE_SYNTHETIC_SENTINEL"
        p = self.policy()
        p["safety_invariants"][EXTRA] = sentinel
        def boom(_):
            raise RuntimeError(sentinel)
        issues = self.errors(p, {ID: self.trusted(check=boom)})
        self.assertTrue(issues)
        self.assertNotIn(sentinel, str(issues))

    def test_missing_and_surplus_result_is_error(self):
        for result in ({}, {EXTRA: "PASS", "other": "PASS"}):
            with self.subTest(result=result):
                issues = self.errors(self.policy(), {ID: self.trusted(check=lambda _, r=result: r)})
                self.assertTrue(any("results incomplete" in x for x in issues), issues)

    def test_adapter_never_overrides_core_rule(self):
        p = self.policy()
        p["safety_invariants"]["no_proven_state_contract"] = "unsafe_ok"
        issues = self.errors(p, {ID: self.trusted()})
        self.assertTrue(any("required safety invariant" in x for x in issues), issues)

    def test_no_adapter_required_for_core_only(self):
        p = self.policy()
        p.pop("safety_adapter")
        p["safety_invariants"].pop(EXTRA)
        self.assertEqual(self.errors(p), [])

    def test_phase_specific_service_adapter_is_additive(self):
        base = self.trusted()
        self.assertTrue(validate_adapter_service(base, {"name": "app"}, {}, "plan"))
        adapter = TrustedSafetyAdapter(ID, "1.0.0", DIGEST, frozenset({EXTRA}),
                                       lambda _: {EXTRA: "PASS"},
                                       lambda svc, ev, phase: {EXTRA: "UNRESOLVED"})
        self.assertTrue(validate_adapter_service(adapter, {"name": "app"}, {}, "pre_mutation"))
        adapter_ok = TrustedSafetyAdapter(ID, "1.0.0", DIGEST, frozenset({EXTRA}),
                                          lambda _: {EXTRA: "PASS"},
                                          lambda svc, ev, phase: {EXTRA: "PASS"})
        self.assertEqual(validate_adapter_service(adapter_ok, {"name": "app"}, {}, "pre_mutation"), [])

    def test_service_checks_require_exact_claim_coverage(self):
        claims = frozenset({EXTRA, "second_rule"})
        responses = (
            {EXTRA: "PASS"},  # omitted claimed rule
            {"second_rule": "PASS"},  # omitted other claimed rule
            {EXTRA: "PASS", "second_rule": "PASS", "extra_rule": "PASS"},
            {"unrelated": "PASS"},  # pass without claims cannot bypass
        )
        for results in responses:
            with self.subTest(results=results):
                adapter = TrustedSafetyAdapter(
                    ID, "1.0.0", DIGEST, claims,
                    lambda _: {EXTRA: "PASS", "second_rule": "PASS"},
                    lambda svc, ev, phase, r=results: r,
                )
                issues = validate_adapter_service(adapter, {"name": "app"}, {}, "pre_mutation")
                self.assertTrue(any("claim coverage mismatch" in x for x in issues), issues)

    def test_service_checks_accept_all_claimed_results_only(self):
        claims = frozenset({EXTRA, "second_rule"})
        adapter = TrustedSafetyAdapter(
            ID, "1.0.0", DIGEST, claims,
            lambda _: {EXTRA: "PASS", "second_rule": "PASS"},
            lambda svc, ev, phase: {EXTRA: "PASS", "second_rule": "PASS"},
        )
        self.assertEqual(validate_adapter_service(adapter, {"name": "app"}, {}, "pre_mutation"), [])

    def test_explicit_null_group_and_manual_null_compose_are_allowed(self):
        p = maintenance.load_policy(ROOT / "examples/native-policy.yaml")
        p["services"][2]["dependencies"]["update_group"] = None
        p["services"][1]["identity"]["compose_project"] = None
        _, errors, warnings = native_policy.structure(p)
        self.assertFalse(errors, errors)
        self.assertFalse(warnings, warnings)

    def test_null_compose_for_auto_service_fails(self):
        p = maintenance.load_policy(ROOT / "examples/native-policy.yaml")
        p["services"][0]["identity"]["compose_project"] = None
        self.assertTrue(any("compose_project" in e for e in self.errors(p)), self.errors(p))

    def test_nontext_docker_ps_output_is_unverified_in_both_schemas(self):
        native = maintenance.load_policy(ROOT / "examples/native-policy.yaml")
        portable = maintenance.load_policy(ROOT / "examples/services.yaml")
        for stdout in (None, [], {}, 123):
            with self.subTest(stdout=stdout):
                with patch("native_policy.subprocess.run",
                           return_value=SimpleNamespace(returncode=0, stdout=stdout)):
                    result = native_policy._runtime(native["services"][0])
                    self.assertEqual(result["status"], "UNVERIFIED")
                with patch("maintenance.subprocess.run",
                           return_value=SimpleNamespace(returncode=0, stdout=stdout)):
                    result = maintenance.docker_snapshot(portable["services"][0])
                    self.assertEqual(result["status"], "unverified")

    def test_secret_bearing_service_invariant_never_leaks_via_cli(self):
        sentinel = "SYNTHETIC_POLICY_SECRET_DO_NOT_ECHO"
        for malformed in (sentinel, {sentinel: True}, [sentinel]):
            for operation in ("validate", "audit", "status", "plan"):
                for fmt in ("text", "json"):
                    with self.subTest(malformed=malformed, operation=operation, fmt=fmt):
                        policy = maintenance.load_policy(ROOT / "examples/native-policy.yaml")
                        policy["services"][0]["topology"]["security_invariants"] = [malformed]
                        with tempfile.TemporaryDirectory() as td:
                            path = Path(td) / "invalid-policy.yaml"
                            path.write_text(yaml.safe_dump(policy), encoding="utf-8")
                            output = io.StringIO()
                            error_output = io.StringIO()
                            with patch("native_policy._runtime",
                                       side_effect=AssertionError("Docker inspection forbidden")), \
                                 contextlib.redirect_stdout(output), \
                                 contextlib.redirect_stderr(error_output):
                                rc = maintenance.main([
                                    "--policy", str(path), "--format", fmt, "--live", operation
                                ])
                        self.assertEqual(rc, 2)
                        self.assertNotIn(sentinel, output.getvalue())
                        self.assertNotIn(sentinel, error_output.getvalue())
                        self.assertIn("unsupported invariant (value withheld)", output.getvalue())
                        if fmt == "json":
                            report = json.loads(output.getvalue())
                            self.assertFalse(report.get("policy_valid", report.get("valid", True)))
                            if operation != "validate":
                                self.assertEqual(len(report["services"]), 3)
                                self.assertTrue(all(
                                    service["runtime"]["status"] == "NOT_CHECKED"
                                    for service in report["services"]
                                ))

    def test_secret_bearing_global_rule_identifier_not_reflected(self):
        sentinel = "SECRET_PRIVATE_GLOBAL_IDENTIFIER"
        p = maintenance.load_policy(ROOT / "examples/native-policy.yaml")
        p["safety_invariants"][sentinel] = True
        errors = self.errors(p)
        self.assertNotIn(sentinel, json.dumps(errors))
        self.assertTrue(any("unsupported global safety invariant" in x for x in errors))


if __name__ == "__main__":
    unittest.main()
