"""Offline acceptance-1 regressions: no Docker, SSH or package installs."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "container-lifecycle-management" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import compose_preflight  # noqa: E402
import doctor  # noqa: E402
import maintenance  # noqa: E402


class AcceptancePreflightTests(unittest.TestCase):
    def test_doctor_reports_environment_without_installing(self):
        status = doctor.check_dependencies()
        self.assertTrue(status["read_only"])
        self.assertFalse(status["dependencies_modified"])
        self.assertIn("pyyaml_available", status)
        self.assertIn("yaml_policy_ready", status)
        self.assertTrue(status["json_policy_ready"])
        self.assertNotIn("pip install", str(status.get("dependencies_modified")))
        self.assertEqual(status["yaml_policy_ready"],
                         status["python_compatible"] and status["pyyaml_available"])

    def test_doctor_missing_dependency_is_nonzero_without_mutating(self):
        with patch.object(doctor.importlib.util, "find_spec", return_value=None), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            code = doctor.main(["--format", "json"])
        payload = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(payload["pyyaml_available"])
        self.assertFalse(payload["yaml_policy_ready"])
        self.assertFalse(payload["dependencies_modified"])
        self.assertNotIn("Traceback", out.getvalue())

    def test_json_policy_ready_even_without_yaml(self):
        with patch.object(doctor.importlib.util, "find_spec", return_value=None):
            status = doctor.check_dependencies()
        self.assertTrue(status["json_policy_ready"])
        self.assertFalse(status["yaml_policy_ready"])

    def test_yaml_missing_dependency_error_does_not_suggest_server_install(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "services.yaml"
            path.write_text("services: []\n", encoding="utf-8")
            with patch.dict(sys.modules, {"yaml": None}):
                with self.assertRaises(maintenance.PolicyError) as caught:
                    maintenance.load_policy(path)
        self.assertIn("doctor.py", str(caught.exception))
        self.assertNotIn("pip install", str(caught.exception))

    def test_doctor_cli_json_readiness_requires_field_check(self):
        with patch.object(doctor.importlib.util, "find_spec", return_value=None), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            exit_code = doctor.main(["--format", "json"])
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertTrue(payload["json_policy_ready"])
        self.assertFalse(payload["yaml_policy_ready"])

    def test_compose_presence_cli_exit_zero_is_not_render_proof(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "compose.yaml"
            p.write_text("services: {}\n", encoding="utf-8")
            with patch.object(compose_preflight.subprocess, "run",
                              side_effect=AssertionError("Docker must not run")), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                exit_code = compose_preflight.main(["--file", str(p), "--format", "json"])
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "FILES_PRESENT_NOT_RENDER_VERIFIED")
        self.assertFalse(payload["source_reproducible"])
        self.assertFalse(payload["runtime_state_verified"])
        self.assertFalse(payload["update_authorized"])

    def test_missing_compose_file_blocks_before_docker(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(compose_preflight.subprocess, "run",
                              side_effect=AssertionError("Docker must not run")):
                result = compose_preflight.inspect_source(
                    [Path(d) / "missing-override.yaml"], render=True)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("source:file_missing_or_unreadable", result["blockers"])
        self.assertFalse(result["update_authorized"])

    def test_all_files_present_does_not_claim_source_rendered(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "compose.yaml"
            p.write_text("services: {}\n", encoding="utf-8")
            with patch.object(compose_preflight.subprocess, "run",
                              side_effect=AssertionError("Docker must not run")):
                result = compose_preflight.inspect_source([p])
        self.assertEqual(result["status"], "FILES_PRESENT_NOT_RENDER_VERIFIED")
        self.assertFalse(result["source_reproducible"])
        self.assertIn("source:render_not_checked", result["blockers"])

    def test_explicit_render_uses_only_quiet_config_with_ordered_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first, second = root / "a.yaml", root / "b.yaml"
            for p in (first, second):
                p.write_text("services: {}\n", encoding="utf-8")
            with patch.object(compose_preflight.subprocess, "run",
                              return_value=type("Result", (), {
                                  "returncode": 0,
                                  "stdout": "NOT_USED_SECRET",
                                  "stderr": "NOT_USED_SECRET",
                              })()) as run:
                result = compose_preflight.inspect_source(
                    [first, second], project_directory=root, render=True)
            argv = run.call_args.args[0]
        self.assertEqual(argv, ["docker", "compose", "--project-directory",
                                str(root), "-f", str(first), "-f", str(second),
                                "config", "--quiet"])
        self.assertEqual(result["status"], "SOURCE_RENDERED_LOCAL_ONLY")
        self.assertTrue(result["compose_render_verified"])
        self.assertFalse(result["source_reproducible"])
        self.assertFalse(result["build_sources_checked"])
        self.assertFalse(result["runtime_state_verified"])
        self.assertFalse(result["update_authorized"])
        self.assertNotIn("NOT_USED_SECRET", repr(result))
        self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_missing_required_interpolation_redacted_and_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "compose.yaml"
            p.write_text("services: {}\n", encoding="utf-8")
            with patch.object(compose_preflight.subprocess, "run",
                              return_value=type("Result", (), {
                                  "returncode": 1, "stdout": "",
                                  "stderr": "SECRET_CANARY_FROM_COMPOSE_ERROR",
                              })()):
                result = compose_preflight.inspect_source([p], render=True)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("source:render_failed", result["blockers"])
        self.assertNotIn("SECRET_CANARY", repr(result))

    def test_compose_unavailable_or_timeout_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "compose.yaml"
            p.write_text("services: {}\n", encoding="utf-8")
            with patch.object(compose_preflight.subprocess, "run",
                              side_effect=OSError("SECRET_TEST_ERROR")):
                result = compose_preflight.inspect_source([p], render=True)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertNotIn("SECRET_TEST_ERROR", repr(result))

    def test_missing_project_directory_and_empty_file_set_refused(self):
        self.assertEqual(compose_preflight.inspect_source([])["status"], "BLOCKED")
        self.assertEqual(compose_preflight.inspect_source([Path("compose.yaml")],
                         project_directory=Path("/a-nonexisting-audit-fixture-987654321")
                         )["status"], "BLOCKED")

    def test_cli_reports_blocker_only_not_missing_path(self):
        with tempfile.TemporaryDirectory() as d:
            secret_path = Path(d) / "SECRET_CANARY_override.yaml"
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = compose_preflight.main([
                    "--file", str(secret_path), "--format", "json", "--render"
                ])
        self.assertEqual(code, 2)
        self.assertNotIn("SECRET_CANARY", out.getvalue())
        self.assertEqual(json.loads(out.getvalue())["status"], "BLOCKED")

    def test_preflight_never_grants_restore_or_update(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "compose.yaml"
            p.write_text("services: {}\n", encoding="utf-8")
            for render in (False, True):
                with self.subTest(render=render), \
                     patch.object(compose_preflight.subprocess, "run",
                                  return_value=type("Result", (), {"returncode": 0})()):
                    status = compose_preflight.inspect_source([p], render=render)
                    self.assertFalse(status["update_authorized"])
                    self.assertFalse(status["runtime_state_verified"])


if __name__ == "__main__":
    unittest.main()
