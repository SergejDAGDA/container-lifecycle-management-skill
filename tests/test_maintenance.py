import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = (Path(__file__).resolve().parents[1] / "skills" /
          "container-lifecycle-management" / "scripts" / "maintenance.py")
spec = importlib.util.spec_from_file_location("maintenance", MODULE)
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


def service(policy="AUTO_SAFE", owner="sandbox"):
    return {
        "name": "test-web",
        "policy": policy,
        "ownership": owner,
        "deployment": {"compose_file": "compose.yaml", "project": "demo", "service": "web"},
        "image": {"current": "example/web:1.0.0"},
        "target": {"image": "example/web:1.0.1"},
        "state": {"complete": True, "binds": [], "volumes": [], "databases": [],
                  "user_files": [], "secret_refs": []},
        "backup": {"required": False},
        "rollback": {"class": "image_only"},
        "health": {"container": "healthy"},
        "smoke": {"profile": "http"},
    }


class PolicyTest(unittest.TestCase):
    def test_normalize_list(self):
        items, errs = maintenance.normalize({"schema_version": "1",
                                              "services": [service()]})
        self.assertEqual(len(items), 1)
        self.assertEqual(errs, [])

    def test_named_mapping(self):
        s = service()
        s.pop("name")
        entries, errs = maintenance.normalize({
            "schema_version": "1", "services": {"test-web": s}
        })
        self.assertEqual(entries[0]["name"], "test-web")
        self.assertFalse(errs)

    def test_schema_migration_not_guessed(self):
        _, errs = maintenance.normalize({"services": []})
        self.assertTrue(errs)

    def test_duplicate(self):
        _, errs = maintenance.normalize({"schema_version": "1",
                                         "services": [service(), service()]})
        self.assertTrue(any("duplicate" in e for e in errs))

    def test_state_missing_blocks(self):
        s = service()
        s["state"]["complete"] = False
        self.assertTrue(any("state contract" in e
                            for e in maintenance.validate_service(s)))

    def test_external_owner_blocks(self):
        self.assertTrue(maintenance.validate_service(service(owner="external_admin")))

    def test_no_touch(self):
        self.assertEqual(maintenance.assessment(service("NO_TOUCH"), None)
                         ["classification"], "EXCLUDED")

    def test_manual(self):
        self.assertEqual(maintenance.assessment(service("MANUAL"), None)
                         ["classification"], "MANUAL_REVIEW")

    def test_unknown_runtime_blocks(self):
        self.assertEqual(maintenance.assessment(service(), None)["classification"],
                         "BLOCKED")

    def test_mutable_identity_drift_blocks(self):
        snap = {"status": "verified", "running": True,
                "configured_image": "example/web:latest"}
        self.assertEqual(maintenance.assessment(service(), snap)["classification"],
                         "BLOCKED")

    def test_candidate_still_gated(self):
        snap = {"status": "verified", "running": True,
                "configured_image": "example/web:1.0.0"}
        self.assertEqual(maintenance.assessment(service(), snap)["classification"],
                         "GATED")

    def test_gated_backup_and_rollback(self):
        s = service("AUTO_GATED")
        s["backup"]["required"] = False
        s["rollback"]["class"] = "unknown"
        self.assertTrue(maintenance.validate_service(s))

    def test_json_cli(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "services.json"
            f.write_text(json.dumps({"schema_version": "1", "services": [service()]}))
            self.assertEqual(maintenance.main(
                ["--policy", str(f), "--format", "json", "validate"]), 0)
            self.assertEqual(maintenance.main(["--policy", str(f), "plan"]), 0)

    def test_secret_values_never_echoed(self):
        s = service()
        s["secret"] = "not-for-logs"
        record = maintenance.assessment(s, None)
        self.assertNotIn("not-for-logs", str(record))


if __name__ == "__main__":
    unittest.main()
