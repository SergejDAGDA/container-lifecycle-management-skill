"""Read-only tests for the optional Compose build-source preflight.

All Compose output is synthetic; these tests never access Docker or user data.
"""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = (Path(__file__).resolve().parents[1] / "skills" /
          "container-lifecycle-management" / "scripts" / "compose_preflight.py")
spec = importlib.util.spec_from_file_location("compose_preflight_rc", MODULE)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class LocalBuildPreflightTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        (self.root / "compose.yaml").write_text("services: {}\n", encoding="utf-8")

    def rendered(self, build=None, **kwargs):
        if build is None:
            build = {"context": str(self.root), "dockerfile": "Dockerfile"}
        payload = {"services": {"web": {"build": build}}, **kwargs}
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(payload),
            stderr="SENSITIVE_PRIVATE_ENV_VALUE",
        )

    def inspect(self, response, *, verify=True):
        with patch.object(preflight.subprocess, "run", return_value=response) as call:
            result = preflight.inspect_source(
                [Path("compose.yaml")], project_directory=self.root,
                render=True, check_build_sources=verify)
        return result, call.call_args

    def test_absent_build_dockerfile_blocks_source_acceptance(self):
        result, args = self.inspect(self.rendered())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("source:dockerfile_missing_or_unreviewed", result["blockers"])
        self.assertEqual(result["build_services_checked"], 1)
        self.assertIn("--format", args.args[0])
        self.assertNotIn("SENSITIVE_PRIVATE_ENV_VALUE", str(result))

    def test_complete_local_build_context_checked(self):
        (self.root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
        result, _ = self.inspect(self.rendered())
        self.assertEqual(result["status"], "SOURCE_RENDERED_LOCAL_ONLY")
        self.assertTrue(result["build_sources_checked"])
        self.assertEqual(result["build_services_checked"], 1)
        self.assertTrue(result["compose_render_verified"])
        self.assertFalse(result["source_reproducible"])  # File presence != full provenance.
        self.assertFalse(result["runtime_state_verified"])
        self.assertFalse(result["update_authorized"])

    def test_standard_image_without_build_has_zero_builds(self):
        response = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps({"services": {"web": {"image": "example:test"}}}),
            stderr="")
        result, _ = self.inspect(response)
        self.assertEqual(result["status"], "SOURCE_RENDERED_LOCAL_ONLY")
        self.assertTrue(result["build_sources_checked"])
        self.assertEqual(result["build_services_checked"], 0)

    def test_inline_dockerfile_is_supported(self):
        result, _ = self.inspect(self.rendered(
            {"context": str(self.root), "dockerfile_inline": "FROM scratch\n"}))
        self.assertEqual(result["status"], "SOURCE_RENDERED_LOCAL_ONLY")

    def test_remote_git_context_needs_independent_provenance(self):
        result, _ = self.inspect(self.rendered(
            {"context": "https://github.com/example/project.git#main"}))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["blockers"],
                         ["source:remote_build_context_needs_provenance"])

    def test_outside_project_context_not_silently_approved(self):
        with tempfile.TemporaryDirectory() as outside:
            result, _ = self.inspect(self.rendered(
                {"context": outside, "dockerfile_inline": "FROM scratch\n"}))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["blockers"],
                         ["source:build_context_outside_project_needs_review"])

    def test_additional_build_context_needs_review(self):
        result, _ = self.inspect(self.rendered(
            {"context": str(self.root), "dockerfile_inline": "FROM scratch\n",
             "additional_contexts": {"base": "https://example.invalid/base.git"}}))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("source:additional_build_contexts_need_review",
                      result["blockers"])

    def test_invalid_compose_json_does_not_leak_values(self):
        response = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='{"services":{"secret":"SENSITIVE_PRIVATE_ENV_VALUE"}',
            stderr="private credentials")
        result, _ = self.inspect(response)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("source:compose_json_invalid", result["blockers"])
        self.assertNotIn("SENSITIVE_PRIVATE_ENV_VALUE", str(result))
        self.assertNotIn("private credentials", str(result))

    def test_build_requires_opt_in_render(self):
        with patch.object(preflight.subprocess, "run") as run:
            result = preflight.inspect_source(
                [Path("compose.yaml")], project_directory=self.root,
                check_build_sources=True, render=False)
        run.assert_not_called()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["blockers"], ["source:build_check_requires_render"])

    def test_original_quiet_render_contract_preserved(self):
        response = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="", stderr="DO_NOT_ECHO_PRIVATE_DATA")
        result, call = self.inspect(response, verify=False)
        self.assertEqual(result["status"], "SOURCE_RENDERED_LOCAL_ONLY")
        self.assertFalse(result["build_sources_checked"])
        self.assertIn("--quiet", call.args[0])
        self.assertTrue(result["compose_render_verified"])
        self.assertFalse(result["source_reproducible"])
        self.assertFalse(result["update_authorized"])

    def test_plain_render_missing_dockerfile_does_not_claim_reproducibility(self):
        # B-01: docker compose config --quiet ignores missing Dockerfiles.
        # A successful render is independent of the build-source check.
        self.assertFalse((self.root / "Dockerfile").exists())
        result, _ = self.inspect(subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr="SENSITIVE_PRIVATE_ENV_VALUE"
        ), verify=False)
        self.assertEqual(result["status"], "SOURCE_RENDERED_LOCAL_ONLY")
        self.assertTrue(result["compose_render_verified"])
        self.assertFalse(result["build_sources_checked"])
        self.assertFalse(result["source_reproducible"])
        self.assertFalse(result["update_authorized"])
        self.assertNotIn("SENSITIVE_PRIVATE_ENV_VALUE", str(result))

    def test_missing_dockerfile_explicit_check_blocks_even_render_evidence(self):
        result, _ = self.inspect(self.rendered())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["compose_render_verified"])
        self.assertFalse(result["source_reproducible"])
        self.assertIn("source:dockerfile_missing_or_unreviewed", result["blockers"])

    def test_cli_never_prints_interpolated_secret(self):
        response = self.rendered({"context": str(self.root),
                                  "dockerfile_inline": "FROM scratch\n"})
        with patch.object(preflight.subprocess, "run", return_value=response):
            from io import StringIO
            from contextlib import redirect_stdout
            out = StringIO()
            with redirect_stdout(out):
                code = preflight.main([
                    "--project-directory", str(self.root),
                    "--file", "compose.yaml", "--render", "--check-build-sources",
                    "--format", "json",
                ])
        self.assertEqual(code, 0)
        self.assertNotIn("SENSITIVE_PRIVATE_ENV_VALUE", out.getvalue())
        self.assertTrue(json.loads(out.getvalue())["build_sources_checked"])


if __name__ == "__main__":
    unittest.main()
