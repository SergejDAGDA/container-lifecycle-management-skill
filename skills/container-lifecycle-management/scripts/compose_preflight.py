#!/usr/bin/env python3
"""Read-only local Compose source reproducibility preflight.

Run ONLY in the deployment filesystem/environment. Remote Docker Engine
paths are not local paths. The optional render only asks Docker Compose to
render configuration; it never contacts Docker to mutate runtime state.

With --check-build-sources, parse the rendered Compose JSON in memory to
check local build context and Dockerfile existence. Never print rendered
config, interpolation values, stderr, Dockerfile content, or secret paths.
This does NOT prove complete build inputs, runtime parity or update authority.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def _decision(
    status: str, blockers: tuple[str, ...], checked: int, *,
    build_sources_checked: bool = False, build_services_checked: int = 0,
) -> dict:
    return {
        "status": status, "blockers": list(blockers),
        "checked_files": checked,
        "build_sources_checked": build_sources_checked,
        "build_services_checked": build_services_checked,
        "compose_render_verified": status == "SOURCE_RENDERED_LOCAL_ONLY",
        # Rendering plus local build-file presence cannot establish complete
        # source/build provenance or parity with a running deployment.
        # These require independent agent/project evidence.
        "source_reproducible": False,
        "runtime_state_verified": False,
        "update_authorized": False,
        "read_only": True,
    }


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def _inspect_build_sources(
    rendered: object, project_root: Path,
) -> tuple[int, tuple[str, ...]]:
    """Inspect only build input *presence*. Never return paths or values."""
    if not isinstance(rendered, dict):
        return 0, ("source:compose_json_invalid",)
    services = rendered.get("services")
    if not isinstance(services, dict):
        return 0, ("source:compose_services_invalid",)
    checked = 0
    for service in services.values():
        if not isinstance(service, dict):
            return checked, ("source:compose_service_invalid",)
        build = service.get("build")
        if build is None:
            continue
        checked += 1
        if isinstance(build, str):
            context, dockerfile, inline = build, "Dockerfile", None
        elif isinstance(build, dict):
            context = build.get("context", ".")
            dockerfile = build.get("dockerfile", "Dockerfile")
            inline = build.get("dockerfile_inline")
            if build.get("additional_contexts"):
                return checked, ("source:additional_build_contexts_need_review",)
        else:
            return checked, ("source:build_definition_invalid",)
        if not isinstance(context, str) or not context:
            return checked, ("source:build_context_invalid",)
        if context.startswith(("https://", "http://", "git://", "github.com/")):
            return checked, ("source:remote_build_context_needs_provenance",)
        context_path = Path(context)
        if not context_path.is_absolute():
            context_path = project_root / context_path
        if not _within(context_path, project_root):
            return checked, ("source:build_context_outside_project_needs_review",)
        if context_path.is_symlink() or not context_path.is_dir():
            return checked, ("source:build_context_missing_or_unreviewed",)
        if inline is not None:
            if not isinstance(inline, str) or not inline.strip():
                return checked, ("source:dockerfile_inline_invalid",)
            if isinstance(build, dict) and "dockerfile" in build:
                return checked, ("source:build_dockerfile_ambiguous",)
        else:
            if not isinstance(dockerfile, str) or not dockerfile:
                return checked, ("source:dockerfile_invalid",)
            dockerfile_path = Path(dockerfile)
            if not dockerfile_path.is_absolute():
                dockerfile_path = context_path / dockerfile_path
            if (not _within(dockerfile_path, project_root)
                    or dockerfile_path.is_symlink()
                    or not dockerfile_path.is_file()):
                return checked, ("source:dockerfile_missing_or_unreviewed",)
    return checked, ()


def inspect_source(
    files: list[Path], *, project_directory: Path | None = None,
    render: bool = False, check_build_sources: bool = False,
) -> dict:
    if not isinstance(files, list) or not files or len(files) > 64:
        return _decision("BLOCKED", ("source:invalid_file_set",), 0)
    if project_directory is not None:
        if (not isinstance(project_directory, Path)
                or not project_directory.is_dir()
                or project_directory.is_symlink()):
            return _decision("BLOCKED", ("source:project_directory_unavailable",), 0)
    checked: list[Path] = []
    for p in files:
        if not isinstance(p, Path) or not str(p):
            return _decision("BLOCKED", ("source:invalid_file_set",), len(checked))
        path = ((project_directory / p) if project_directory is not None
                else p)
        if path.is_symlink():
            return _decision("BLOCKED", ("source:unreviewed_symlink",), len(checked))
        if not path.is_file():
            return _decision("BLOCKED", ("source:file_missing_or_unreadable",), len(checked))
        checked.append(path)
    if check_build_sources and not render:
        return _decision("BLOCKED", ("source:build_check_requires_render",), len(checked))
    if not render:
        return _decision("FILES_PRESENT_NOT_RENDER_VERIFIED",
                         ("source:render_not_checked",), len(checked))
    command = ["docker", "compose"]
    if project_directory is not None:
        command.extend(["--project-directory", str(project_directory)])
    for p in checked:
        command.extend(["-f", str(p)])
    command.extend(["config", "--format", "json"] if check_build_sources else
                   ["config", "--quiet"])
    try:
        finished = subprocess.run(
            command, capture_output=True, text=True,
            timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return _decision("BLOCKED", ("source:compose_cli_unavailable",), len(checked))
    if finished.returncode != 0:
        return _decision("BLOCKED", ("source:render_failed",), len(checked))
    if check_build_sources:
        try:
            document = json.loads(finished.stdout)
        except (ValueError, TypeError):
            return _decision("BLOCKED", ("source:compose_json_invalid",), len(checked))
        project_root = project_directory or checked[0].parent
        build_checked, blockers = _inspect_build_sources(document, project_root)
        if blockers:
            return _decision("BLOCKED", blockers, len(checked),
                             build_services_checked=build_checked)
        return _decision("SOURCE_RENDERED_LOCAL_ONLY", (), len(checked),
                         build_sources_checked=True,
                         build_services_checked=build_checked)
    return _decision("SOURCE_RENDERED_LOCAL_ONLY", (), len(checked))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="No-mutation local Compose source preflight")
    parser.add_argument("--file", type=Path, action="append", required=True,
                        help="One of the exact ordered Compose source files")
    parser.add_argument("--project-directory", type=Path)
    parser.add_argument("--render", action="store_true",
                        help="Opt-in: render local Compose config without printing values")
    parser.add_argument("--check-build-sources", action="store_true",
                        help="With --render: also check local build context/Dockerfile presence")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args(argv)
    outcome = inspect_source(args.file, project_directory=args.project_directory,
                             render=args.render,
                             check_build_sources=args.check_build_sources)
    if args.format == "json":
        print(json.dumps(outcome, indent=2, sort_keys=True))
    else:
        print(outcome["status"] + " (files checked: " + str(outcome["checked_files"]) + ")")
        for code in outcome["blockers"]:
            print("  " + code)
        print("READ-ONLY; local checks never authorize an update")
    return 0 if outcome["status"] != "BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
