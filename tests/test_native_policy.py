"""Synthetic tests for extended project-maintenance policies."""
import importlib.util
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SCRIPT = BASE / "skills" / "container-lifecycle-management" / "scripts"
sys.path.insert(0, str(SCRIPT))
import maintenance  # noqa: E402
import native_policy  # noqa: E402


class ExtendedPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = BASE / "examples" / "native-policy.yaml"

    def test_synthetic_fixture_is_structurally_valid(self):
        data = maintenance.load_policy(self.path)
        services, errors, warnings = native_policy.structure(data)
        self.assertFalse(errors, errors)
        self.assertEqual(len(services), 3)
        self.assertFalse(warnings, warnings)

    def test_vendor_namespaced_schema(self):
        data = maintenance.load_policy(self.path)
        data["schema"] = "independent-host-maintenance/v1"
        _, errors, _ = native_policy.structure(data)
        self.assertFalse(errors, errors)

    def test_unknown_schema_rejected(self):
        data = maintenance.load_policy(self.path)
        data["schema"] = "anything-goes/v3"
        _, errors, _ = native_policy.structure(data)
        self.assertTrue(errors)

    def test_safety_rule_cannot_be_downgraded(self):
        data = maintenance.load_policy(self.path)
        data["safety_invariants"]["security_release_gate_bypass"] = "allowed"
        _, errors, _ = native_policy.structure(data)
        self.assertTrue(any("security_release_gate_bypass" in x for x in errors))

    def test_manual_group_member_blocks_auto_safe(self):
        data = maintenance.load_policy(self.path)
        services, errors, _ = native_policy.structure(data)
        self.assertFalse(errors)
        records = native_policy.assess_native(data, services)
        self.assertEqual(records[0]["classification"], "BLOCKED")
        self.assertTrue(any("MANUAL" in x for x in records[0]["issues"]))

    def test_explicit_component_alias_resolves_exact_compose_identity(self):
        data = maintenance.load_policy(self.path)
        services, errors, warnings = native_policy.structure(data)
        self.assertFalse(errors, errors)
        self.assertFalse(warnings, warnings)
        resolved, problems = native_policy.resolve_group(
            "synthetic-web-stack", data["service_groups"]["synthetic-web-stack"], services)
        self.assertFalse(problems, problems)
        self.assertEqual({s["name"] for s in resolved},
                         {"synthetic-web", "synthetic-worker"})

    def test_missing_alias_fails_group_validation(self):
        data = maintenance.load_policy(self.path)
        del data["service_groups"]["synthetic-web-stack"]["component_aliases"]
        _, errors, _ = native_policy.structure(data)
        self.assertTrue(any("synthetic-background" in x and "unresolved" in x
                            for x in errors), errors)
        self.assertEqual(maintenance.main(
            ["--policy", str(self.path), "validate"]), 0)

    def test_mistyped_compose_target_fails_closed(self):
        data = maintenance.load_policy(self.path)
        data["service_groups"]["synthetic-web-stack"]["component_aliases"][
            "synthetic-background"]["compose_service"] = "wrong-service"
        _, errors, _ = native_policy.structure(data)
        self.assertTrue(any("not in owning record" in x for x in errors), errors)

    def test_wrong_policy_owner_fails_closed(self):
        data = maintenance.load_policy(self.path)
        data["service_groups"]["synthetic-web-stack"]["component_aliases"][
            "synthetic-background"]["policy_service"] = "synthetic-protected"
        _, errors, _ = native_policy.structure(data)
        self.assertTrue(errors)

    def test_alias_to_other_update_group_fails_closed(self):
        data = maintenance.load_policy(self.path)
        data["services"][1]["dependencies"]["update_group"] = "other-group"
        _, errors, _ = native_policy.structure(data)
        self.assertTrue(any("belongs to another group" in x for x in errors), errors)

    def test_unlisted_alias_fails_validation(self):
        data = maintenance.load_policy(self.path)
        data["service_groups"]["synthetic-web-stack"]["component_aliases"][
            "orphan-component"] = {"policy_service": "synthetic-worker", "compose_service": "worker"}
        _, errors, _ = native_policy.structure(data)
        self.assertTrue(any("not listed" in x for x in errors), errors)

    def test_redundant_alias_not_accepted(self):
        data = maintenance.load_policy(self.path)
        data["service_groups"]["synthetic-web-stack"]["component_aliases"][
            "synthetic-web"] = {"policy_service": "synthetic-web", "compose_service": "web"}
        _, errors, _ = native_policy.structure(data)
        self.assertTrue(any("unnecessary/conflicting" in x for x in errors), errors)

    def test_bad_alias_type_reports_error_not_exception(self):
        data = maintenance.load_policy(self.path)
        data["service_groups"]["synthetic-web-stack"]["component_aliases"][
            "synthetic-background"] = "guess"
        _, errors, _ = native_policy.structure(data)
        self.assertTrue(any("requires policy_service" in x for x in errors), errors)

    def test_protected_stack_never_inspected_even_live(self):
        data = maintenance.load_policy(self.path)
        services, _, _ = native_policy.structure(data)
        protected = services[2]
        observed = native_policy.assess_native(data, [protected], live=True)
        self.assertEqual(observed[0]["classification"], "EXCLUDED")
        self.assertEqual(observed[0]["runtime"]["status"], "NOT_CHECKED")

    def test_explicit_state_contract_required(self):
        data = maintenance.load_policy(self.path)
        del data["services"][0]["state_contract"]["named_volumes"]
        _, errors, _ = native_policy.structure(data)
        self.assertTrue(any("named_volumes" in x for x in errors))

    def test_unknown_owner_blocks_auto_mode(self):
        data = maintenance.load_policy(self.path)
        data["services"][0]["ownership"] = "external_admin"
        _, errors, _ = native_policy.structure(data)
        self.assertTrue(any("external/unknown" in x for x in errors))

    def test_cli_reports_the_actual_policy_namespace(self):
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            code = maintenance.main(
                ["--policy", str(self.path), "--format", "json", "plan"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(capture.getvalue())["schema"], "demo-maintenance/v1")

    def test_native_cli_validate_and_plan(self):
        self.assertEqual(maintenance.main(
            ["--policy", str(self.path), "validate"]), 0)
        self.assertEqual(maintenance.main(
            ["--policy", str(self.path), "plan"]), 0)

    def test_mutation_script_has_no_updater(self):
        self.assertNotIn("update-auto", maintenance.SUPPORTED)
        self.assertNotIn("update", maintenance.SUPPORTED)

    def test_sensitive_values_not_emitted(self):
        data = maintenance.load_policy(self.path)
        data["services"][0]["state_contract"]["secrets"] = ["secret_reference_only"]
        records = native_policy.assess_native(data, data["services"])
        self.assertNotIn("secret_reference_only", str(records))


if __name__ == "__main__":
    unittest.main()
