# Codex installation and Skill ID migration — Container Lifecycle Management

## Proposed v0.6.0 migration (not yet published)

1. Do not install from PRs or floating `main`. First verify the published non-draft GitHub Release, exact final tag-to-commit identity, package `VERSION`, plugin manifests and passing CI for the accepted revision.
2. Preserve the existing `maintain-server-containers` v0.5.1 installed payload as an **inactive**, out-of-skill-root rollback snapshot before any replacement. Do not remove or overwrite it during repository rename.
3. Install **only** `skills/container-lifecycle-management/` from the verified `v0.6.0` release to the approved skills root; no new or existing project, server, Docker container, persistent data or backup is modified by installation.
4. Check that frontmatter `name: container-lifecycle-management`, `VERSION: 0.6.0` and `$container-lifecycle-management` all match. In a fresh Codex Desktop chat, perform a strictly read-only invocation; do not test a live operation.
5. Only after passing the new identity test, retire the old **active** `maintain-server-containers` directory individually while retaining the rollback snapshot outside all active skills roots. Do not treat it as a runtime alias. Verify the old active directory is no longer discovered in another fresh chat.
6. SandBox-Server's `maintain-server-containers/safety-adapter/v1` programmatic API remains unchanged. Migrate its project-local **skill calls** separately, without replacing this API or invoking Docker.
7. Record installed package origin, exact release commit, active path, rollback path and any unverified environment boundaries.

## Historical v0.5.0/v0.4.0 update procedures

The following archival instructions intentionally use the old installed Skill ID, old release paths and their original version numbers. They document historical installations, **not** instructions to install the v0.6.0 candidate. Do not globally rewrite their paths or invoke them as a current migration procedure.

# Codex installation and update — Maintain Server Containers v0.5.0 (publication pending)

> This section supersedes the v0.4.0-only update target **after** v0.5.0 is published. Do not install from an unmerged PR, a floating branch, or an unpublished tag. The installed baseline remains v0.4.0 until a separately approved update.

## v0.5.0 update after publication

1. Confirm the actual published GitHub tag and non-draft Release `v0.5.0` are present and refer to the accepted final `main` SHA, and CI passes at that exact SHA.
2. Check `skills/maintain-server-containers/VERSION`, `plugin.json` and `.claude-plugin/plugin.json` all equal `0.5.0`.
3. In Codex Desktop, locate the **existing** user-scope `maintain-server-containers` skill and take a local rollback copy outside any active skills directory; install **only the canonical skill directory** from the published v0.5.0 tag. Do not alter other installed skills or server resources.
4. Restart/refresh skill discovery if required and run `$maintain-server-containers` in **read-only** mode to verify actual native invocation. If local Codex egress/transport fails, report `ENVIRONMENT / NOT VERIFIED`; do not grant elevated network access automatically.
5. Report exact tag→SHA, installed path/version and rollback copy; do not modify Docker applications, databases, volumes, backup locations or server policy during installation.

The server administrator, not this update workflow, owns the physical server/disks, host backup storage and synchronization. The skill guides application-scoped Docker operations only when authorized.

---

# Codex installation and update — Maintain Server Containers v0.4.0

Canonical public repository:
`https://github.com/SergejDAGDA/agent-maintain-server-containers`

Exact release source:
`https://github.com/SergejDAGDA/agent-maintain-server-containers/tree/v0.4.0/skills/maintain-server-containers`

## Safety-first update (recommended)

The v0.4.0 tag and GitHub Release are created through a separately authorized **manual GitHub publication** after both workflows pass on the exact merged `main` commit SHA. There is no custom release workflow for v0.4.0. Do not install from a PR or from `main` before that published Release exists.

For an existing v0.3.0 installation, keep the current copy active until the
v0.4.0 GitHub Release and tag are verified. This is an explicitly authorized
local Codex skill upgrade, not a server maintenance task.

Tell Codex to perform a controlled, **local-only** installation:

> Update my existing Codex skill `maintain-server-containers` to exactly
> `v0.4.0` from the GitHub release linked above. First inspect all existing
> user/project skill locations and the installed skill content. Do not edit
> the internal Codex runtime cache, unrelated skills, project-owned
> `maintenance/services.yaml`, or any Docker services. Verify the GitHub
> release exists and that both plugin manifests and
> `skills/maintain-server-containers/VERSION` say `0.4.0`.
> Download or clone the **tagged** repository into a temporary directory,
> validate the canonical skill folder, then back up the currently installed
> copy **outside all active skill discovery paths**. Replace only the
> `maintain-server-containers` directory using a safe staged update.
> Preserve unrelated files, and roll back to the backup if installation or
> verification fails. Avoid two active copies in different skill locations.
> Run the Python example policy validation tests in the cloned repository
> without contacting Docker, and report the release tag, commit SHA, final
> installed `SKILL.md` path, installed `VERSION`, and any problems.
> Do not modify servers, volumes, running containers, secrets, or Git repos
> except the intended local skill installation and its local backup.

This prompt intentionally leaves platform-specific install locations for
Codex to discover: Codex versions and skill-install methods can differ.
The source is **pinned to a tag**, not to `main`.

## New installation (when the skill is absent)

If your Codex environment offers `$skill-installer`, you may request:

```text
$skill-installer install https://github.com/SergejDAGDA/agent-maintain-server-containers/tree/v0.4.0/skills/maintain-server-containers
```

The official installer generally **refuses to overwrite** an existing
directory. For updates, use the controlled backup-and-replace prompt above,
rather than deleting a skill blindly. If your Codex does not provide
`$skill-installer`, an agent may clone the tagged repository and place
**only** `skills/maintain-server-containers/` in the active user or
repository skills directory. Check available paths in the current Codex
version; do not guess where the installed skill currently lives.

## Verification

1. The public GitHub release is actually published (not merely a commit or
   proposed tag), and the source is exactly the `v0.4.0` tag.
2. Both repository manifests have version `0.4.0`; the installed
   `maintain-server-containers/VERSION` contains only `0.4.0`.
3. `SKILL.md`, `scripts/maintenance.py`, and the `references/` documents
   are present in the **same installed skill folder**.
4. The standalone source checkout passes:
   ```sh
   python skills/maintain-server-containers/scripts/doctor.py --format json
   python -m unittest discover -s tests -v
   python skills/maintain-server-containers/scripts/maintenance.py --policy examples/services.yaml validate
   python skills/maintain-server-containers/scripts/maintenance.py --policy examples/native-policy.yaml validate
   ```
   For YAML policies, use an existing reviewed local virtual environment with PyYAML. A controlled, explicitly approved local test-environment setup may install the declared requirements separately. Never install packages on the inspected server as a side effect of read-only acceptance. For JSON policies, check `json_policy_ready` even if doctor returns 2 for YAML readiness.
5. Restart the Codex session if skill discovery does not refresh. Invoke
   `$maintain-server-containers` first with a **read-only** request.

## First acceptance prompt (no service changes)

```text
Use $maintain-server-containers to audit the Docker Compose projects
available in this environment in read-only mode. Discover the project-owned
policy, existing server instructions and the exact Compose service/volume
identities. Do not pull images, stop/recreate containers, modify Compose
files, run backup captures, restore data or change network/access. Report
what was verified, what remains unknown, blocked services and a suggested
next maintenance plan. Do not infer authorization from a passing policy.
```

**Warning:** v0.4.0 does not include a deterministic production Docker
updater or protected independent disaster-recovery service. Synthetic CI
success is not proof that real applications are safe to upgrade.


Canonical public repository:
`https://github.com/SergejDAGDA/agent-maintain-server-containers`

Exact release source:
`https://github.com/SergejDAGDA/agent-maintain-server-containers/tree/v0.4.0/skills/maintain-server-containers`

## Safety-first update (recommended)

The v0.4.0 tag and GitHub Release are created through a separately authorized **manual GitHub publication** after both workflows pass on the exact merged `main` commit SHA. There is no custom release workflow for v0.4.0. Do not install from a PR or from `main` before that published Release exists.

For an existing v0.3.0 installation, keep the current copy active until the
v0.4.0 GitHub Release and tag are verified. This is an explicitly authorized
local Codex skill upgrade, not a server maintenance task.

Tell Codex to perform a controlled, **local-only** installation:

> Update my existing Codex skill `maintain-server-containers` to exactly
> `v0.4.0` from the GitHub release linked above. First inspect all existing
> user/project skill locations and the installed skill content. Do not edit
> the internal Codex runtime cache, unrelated skills, project-owned
> `maintenance/services.yaml`, or any Docker services. Verify the GitHub
> release exists and that both plugin manifests and
> `skills/maintain-server-containers/VERSION` say `0.4.0`.
> Download or clone the **tagged** repository into a temporary directory,
> validate the canonical skill folder, then back up the currently installed
> copy **outside all active skill discovery paths**. Replace only the
> `maintain-server-containers` directory using a safe staged update.
> Preserve unrelated files, and roll back to the backup if installation or
> verification fails. Avoid two active copies in different skill locations.
> Run the Python example policy validation tests in the cloned repository
> without contacting Docker, and report the release tag, commit SHA, final
> installed `SKILL.md` path, installed `VERSION`, and any problems.
> Do not modify servers, volumes, running containers, secrets, or Git repos
> except the intended local skill installation and its local backup.

This prompt intentionally leaves platform-specific install locations for
Codex to discover: Codex versions and skill-install methods can differ.
The source is **pinned to a tag**, not to `main`.

## New installation (when the skill is absent)

If your Codex environment offers `$skill-installer`, you may request:

```text
$skill-installer install https://github.com/SergejDAGDA/agent-maintain-server-containers/tree/v0.4.0/skills/maintain-server-containers
```

The official installer generally **refuses to overwrite** an existing
directory. For updates, use the controlled backup-and-replace prompt above,
rather than deleting a skill blindly. If your Codex does not provide
`$skill-installer`, an agent may clone the tagged repository and place
**only** `skills/maintain-server-containers/` in the active user or
repository skills directory. Check available paths in the current Codex
version; do not guess where the installed skill currently lives.

## Verification

1. The public GitHub release is actually published (not merely a commit or
   proposed tag), and the source is exactly the `v0.4.0` tag.
2. Both repository manifests have version `0.4.0`; the installed
   `maintain-server-containers/VERSION` contains only `0.4.0`.
3. `SKILL.md`, `scripts/maintenance.py`, and the `references/` documents
   are present in the **same installed skill folder**.
4. The standalone source checkout passes:
   ```sh
   python skills/maintain-server-containers/scripts/doctor.py --format json
   python -m unittest discover -s tests -v
   python skills/maintain-server-containers/scripts/maintenance.py --policy examples/services.yaml validate
   python skills/maintain-server-containers/scripts/maintenance.py --policy examples/native-policy.yaml validate
   ```
   For YAML policies, use an existing reviewed local virtual environment with PyYAML. A controlled, explicitly approved local test-environment setup may install the declared requirements separately. Never install packages on the inspected server as a side effect of read-only acceptance. For JSON policies, check `json_policy_ready` even if doctor returns 2 for YAML readiness.
5. Restart the Codex session if skill discovery does not refresh. Invoke
   `$maintain-server-containers` first with a **read-only** request.

## First acceptance prompt (no service changes)

```text
Use $maintain-server-containers to audit the Docker Compose projects
available in this environment in read-only mode. Discover the project-owned
policy, existing server instructions and the exact Compose service/volume
identities. Do not pull images, stop/recreate containers, modify Compose
files, run backup captures, restore data or change network/access. Report
what was verified, what remains unknown, blocked services and a suggested
next maintenance plan. Do not infer authorization from a passing policy.
```

**Warning:** v0.4.0 does not include a deterministic production Docker
updater or protected independent disaster-recovery service. Synthetic CI
success is not proof that real applications are safe to upgrade.
