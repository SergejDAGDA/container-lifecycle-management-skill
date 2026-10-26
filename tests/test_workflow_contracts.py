"""Static, non-execution boundary assertions for agent-level deployment workflows.

These tests do not claim that Docker installation/rollback has been tested.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "container-lifecycle-management"
sys.path.insert(0, str(SKILL / "scripts"))
import maintenance


class DeploymentWorkflowTest(unittest.TestCase):
    def test_deployment_workflows_are_discoverable(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("deploy-project <project>", text)
        self.assertIn("deploy-repository <repository-url>", text)

    def test_core_operation_does_not_require_other_skills(self):
        guide = (SKILL / "references" / "project-deployment.md").read_text(encoding="utf-8")
        self.assertIn("optional integrations", guide)
        self.assertIn("If absent or blocked", guide)
        self.assertIn("DEPLOYED_RECORD_SYNC_PENDING", guide)

    def test_repository_first_install_limits_authority(self):
        text = (SKILL / "references" / "repository-deployment.md").read_text(encoding="utf-8")
        for required in (
            "Docker socket", "untrusted", "public exposure",
            "existing application data", "MANUAL", "no pre-existing application user data",
            "bounded first installation",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_cli_has_no_unsupported_mutation_subcommands(self):
        self.assertNotIn("deploy-project", maintenance.SUPPORTED)
        self.assertNotIn("deploy-repository", maintenance.SUPPORTED)

    def test_existing_and_new_synthetic_examples_validate(self):
        examples = ROOT / "examples"
        for name in ("services.yaml", "native-policy.yaml",
                     "project-managed.yaml", "repository-managed.yaml"):
            with self.subTest(name=name):
                data = maintenance.load_policy(examples / name)
                if data.get("schema_version") == "1":
                    _, errors = maintenance.normalize(data)
                else:
                    import native_policy
                    _, errors, _ = native_policy.structure(data)
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
