# Container Lifecycle Management

[Русская версия](README.ru.md)

**A reusable Agent Skill for policy-driven Docker application lifecycle management: installation, deployment, updates, backup/recovery and controlled rebuilds across local and remote environments.**

GitHub repository: `SergejDAGDA/container-lifecycle-management-skill`

Installed Skill ID (v0.6.0 candidate): `container-lifecycle-management`

Invocation for candidate v0.6.0: `$container-lifecycle-management`.

**Compatibility:** published versions through v0.5.1 used the installed Skill ID `$maintain-server-containers`; this is historical and **not** an alias for the new Skill ID. The safety-adapter API identity `maintain-server-containers/safety-adapter/v1` remains **unchanged** for existing SandBox-Server adapters. The GitHub repo was renamed independently; the candidate v0.6.0 is not published or installed until separately accepted.

**Published releases:** check the [GitHub Releases page](https://github.com/SergejDAGDA/container-lifecycle-management-skill/releases); the installable package version is declared in `skills/container-lifecycle-management/VERSION` and both plugin manifests. Updating a separately installed Agent Skill is an explicit action; publishing repository files does not automatically replace an existing installation. The bundled CLI can validate a portable project policy and run read-only policy/runtime audits, status and planning. The skill also defines the complete agent-operated upgrade workflow, but it does **not** ship a production mutation executor. Do not confuse a passing schema check with a verified safe deployment.

## Architecture and security audit (13 October 2026)

The reviewed code and synthetic CI through H31 are summarized in the
[security and architecture audit](docs/SECURITY-ARCHITECTURE-AUDIT-2026-10-13.md).
The audit confirms a passing read-only v0.2.0 baseline and substantial
**synthetic** disaster-recovery contract coverage, but **NO-GO** for claiming
a production mutation executor, independently secured off-host backup, or
trusted remote monotonic anchor service. This repository update does not
upgrade any separately installed skill. PR #22 completed bounded
input hardening; this v0.3.0 release does not add production write authority.

## Post-audit hardening (included in v0.3.0)

After the [13 October architecture audit](docs/SECURITY-ARCHITECTURE-AUDIT-2026-10-13.md),
portable v1 validation is deliberately strict: undeclared policy fields,
including unreviewed safety extensions, are errors rather than invisible
permissions. Extended project-specific semantics require explicit, reviewed
normalization or a native project policy. Malformed synthetic runtime
evidence is rejected; portable `--live` uses a minimal Docker inspect
projection rather than requesting the full container record.

**Distribution and verification boundary:** source changes on `main` do not
update an installed Agent Skill. Python requirements and the CI test toolchain
are not a reproducible locked production distribution; install/package
integrity attestation and immutable tooling pins remain separate release
work. Even with every CI test green, this repository still has **no**
production Docker mutation executor, independent off-host backup
service, or protected remote monotonic-witness authority. Do not infer
operational safety from the experimental H31 tests.

## Install or update in Codex

Follow the [version-pinned Codex update guide](docs/CODEX-INSTALL-UPDATE.md)
and use the canonical skill folder from the [latest published release](https://github.com/SergejDAGDA/container-lifecycle-management-skill/releases/latest).
The installable folder contains a `VERSION` marker for exact-version checks.
Updating a repository checkout or plugin marketplace **does not automatically
replace an older user-scope skill**. Back up an existing installation and
check duplicate skill locations before updating.

## Practical read-only acceptance (included in v0.4.0)

The first real read-only audit and a Codex retrospective informed the new
fail-closed preflight, explicit runtime-to-policy coverage summary and clear
machine-status versus agent-finding distinctions. The PR #26 baseline was independently accepted with 393 offline tests on
Windows and Linux, plus disposable Linux Compose/Restic integration.
Release-specific tests add to that baseline. The helper still does not scan
all hosts automatically or authorize changes.

An initial real-world audit exposed an **interpreter dependency gap**:
installing a skill does not install PyYAML into every Python interpreter.
The skill now includes a standard-library-only
[`scripts/doctor.py`](skills/container-lifecycle-management/scripts/doctor.py).
Run it with the same interpreter planned for `maintenance.py`.
Prefer an existing **local** Codex virtual environment with PyYAML;
do not install packages on the inspected server merely for a read-only audit.

Backup assurance is a separate agent workflow: `backup-audit [service]` checks existing jobs and event-based checkpoints, per-service data/source coverage, retention and protected historical milestones, exact snapshot evidence, off-host independence and alert delivery **read-only**; `backup-verify <service>` tests an owner-authorized isolated restore. See [backup-control.md](skills/container-lifecycle-management/references/backup-control.md). The skill does not install a backup scheduler, automatically delete snapshots or claim production restore success from synthetic CI.

A separate [Compose source preflight](skills/container-lifecycle-management/scripts/compose_preflight.py)
checks an explicit ordered list of Compose files **on the host where the
files exist**. The optional `--render` flag invokes
`docker compose config --quiet` after source/environment review;
`--render --check-build-sources` checks rendered **local** build context and
Dockerfile presence via in-memory Compose JSON. Missing, remote or extra
build contexts block the local-source assertion until independently reviewed.
No interpolated output, source values or raw errors are emitted. Machine
`compose_render_verified=true` means only a successful local Compose render;
`source_reproducible=false` is deliberately retained even after checking
local Dockerfile presence, because complete build provenance and runtime
parity require independent evidence. Neither mode authorizes updates. Neither successful
presence checks nor a local render validates runtime state or authorizes
updates. Missing temporary overrides, missing required environment,
unmanaged services, incomplete aggregate identities, and unverified
restore capability are blocking findings. External-admin services remain
**NO_TOUCH**; provide feedback to their administrator, never change them
unilaterally.

These audited preflight safeguards ship with `v0.4.0` (PR #25 and #26).
The `v0.4.0` GitHub Release is published **manually** only after a merged commit passes both CI workflows on `main`. Merging the release PR does not publish a tag. Verify the exact tag commit and the published Release separately.
An older installed `v0.3.0` remains unchanged until explicitly updated
from the published `v0.4.0` tag. GitHub `main` is not an installation source.

## Why

Routine Docker maintenance is more complex than pulling `latest`. Real deployments may contain persistent accounts, databases, media files, encrypted credentials, externally managed stacks and schema migrations. Upgrading application binaries should not silently replace any of that state.

The aim is to make repeatable, understandable maintenance possible with **one bounded user request** instead of a separate confirmation for every pull, recreate and health check, while retaining real safety and ownership boundaries.

## What it does

- Discovers Docker Compose service and deployment ownership.
- Helps establish a project-owned maintenance policy.
- Audits images, runtime identity, mount boundaries, health and policy drift.
- Plans version updates from authoritative upstream releases and changelogs.
- Classifies update eligibility as `AUTO_SAFE`, `AUTO_GATED`, `MANUAL`, `PIN_ONLY` or `NO_TOUCH`.
- Defines backup/recovery, smoke tests, dependency groups and rollback rules.
- Guides authorized agents through bounded updates and accurate mutation reporting.
- Defines a targeted `rebuild` workflow for existing applications with explicitly disposable state, without sacrificing personal files or reproducible deployment sources.
- Keeps instance-specific hosts, accounts, paths and service profiles **out of the public skill**.

The read-only helper deliberately does not pull images, change deployment files or recreate containers.

**Extended-policy compatibility:** in addition to the portable `schema_version: "1"` format, the bundled CLI recognizes namespaced `<project>-maintenance/v1` policies with `policy_class`, `identity.compose_services`, `state_contract.completeness` and dependency groups. The adapter preserves this richer source structure and never rewrites a project's policy. See [synthetic extended example](examples/native-policy.yaml). This is format compatibility, not an automatic approval to update.

## Quick start

### Install as an Agent Skill

For an agent that supports the Agent Skills directory format, clone the repository and install/copy only the canonical skill directory:

```text
skills/container-lifecycle-management/
  SKILL.md
  agents/openai.yaml
  references/
  scripts/
```

For Codex, place that directory in the configured user or project skills location. For Claude Code, use the provided plugin manifest/compatible skill directory. Follow your agent host's current installation instructions.

### Set up the CLI

Python 3.10+ is required. For YAML policies, first check PyYAML in the **same** Python interpreter using the noninstalling doctor. Reuse an existing reviewed local environment. JSON policies do not need PyYAML. Do not install dependencies on an inspected server for a read-only audit.

```sh
python skills/container-lifecycle-management/scripts/doctor.py --format json
python skills/container-lifecycle-management/scripts/maintenance.py --policy examples/services.yaml validate
python skills/container-lifecycle-management/scripts/maintenance.py --policy examples/services.yaml plan
python skills/container-lifecycle-management/scripts/maintenance.py --policy examples/native-policy.yaml validate
```

Read-only live metadata inspection:

```sh
python skills/container-lifecycle-management/scripts/maintenance.py --policy maintenance/services.yaml --live audit
python skills/container-lifecycle-management/scripts/maintenance.py --policy maintenance/services.yaml --live --format json status
```

Note: options such as `--format` are top-level arguments and must appear before the operation name.

`--live` uses only read-only Docker `ps` and `inspect` operations for a uniquely matched Compose service. It never assumes that Docker metadata proves application-level data recovery.

### Invoke in chat

```text
$container-lifecycle-management audit
Inspect the Compose server and show me version, health and state risks. Do not make changes.
```

```text
$container-lifecycle-management plan
Check authoritative upstream releases and prepare safe, grouped update candidates.
```

```text
$container-lifecycle-management update-auto
Update services eligible under the project policy, preserving user data and performing all required checks and safe rollbacks. Skip every blocked or manual service.
```

The last command is an *agent-level workflow request*, **not a command implemented by the bundled read-only Python CLI**. The agent must have the relevant authorized deployment and backup tools and must follow all gates in `SKILL.md`. It must not improvise a missing recovery mechanism.


## Install a new third-party application from a repository

The skill also defines `deploy-repository` for installing a new external application
into an existing Compose server, starting with an explicit Git repository URL:

```text
$container-lifecycle-management deploy-repository https://github.com/example-org/example-app
Set it up as an isolated Docker Compose application on my server, check its
dependencies, state and network exposure, and register it for future maintenance.
```

The agent inspects source/release metadata and upstream Dockerfiles/Compose as
**untrusted input**, selects a reproducible version, checks conflicts with
existing services, prepares deployment/configuration and protected persistent
storage, performs the bounded initial deployment, verifies health and records
the installed app in the server's existing maintenance policy.

One explicit request covers normal reversible steps: the agent should not ask
whether to create every folder or dependency. It must **not** silently grant
privileged mode, host Docker socket access, broad writable mounts, expose
administrative endpoints publicly, or overwrite existing user data. Missing
third-party credentials or significant exposure/privilege changes require
a focused decision. Generated secrets stay in protected storage, not Git or logs.

A newly installed application defaults to `MANUAL` maintenance until an
independent update-safety classification can be proven. Optional other
Agent Skills never control whether core deployment can proceed.

See [repository-deployment.md](skills/container-lifecycle-management/references/repository-deployment.md)
for the first-install protocol. This is an **agent-operated workflow**;
the bundled read-only CLI is not yet a production installer.


## Deployment layout profiles

The skill now defines explicit **default layouts** for new Docker Compose
deployments: system-managed single-host Linux, remotely managed Linux over
SSH, and a per-user/rootless Linux workstation. Existing project conventions
**always take precedence**; do not migrate paths or data merely to match a
template.

When no standard exists, the proposed system-managed layout separates
versioned deployment sources (`/srv/compose/<app>/`), optional host-bind
state (`/srv/data/<app>/`), and protected runtime secrets
(`/etc/compose-secrets/<app>/`). Named Docker volumes remain engine-managed.
For a remote server, distinguish the management project's canonical
non-secret sources from the actual server-side Compose/build files, verify
their parity, and interpret bind paths on the **Docker daemon's host**.

See [deployment-layouts.md](skills/container-lifecycle-management/references/deployment-layouts.md)
for environment selection, source ownership, storage boundaries, SSH,
Compose project names, secret handling and pre-deploy/acceptance receipts.
These paths are portable **recommendations**, not Docker/FHS requirements
and not a reason to rewrite existing installations.

## Clean rebuild of an existing application

For a broken or obsolete existing app whose models, caches or unused accounts
can be discarded **with the owner's explicit approval**, use a targeted manual
workflow rather than inventing an update or treating the service as a fresh
`deploy-repository` installation:

```text
$container-lifecycle-management rebuild doc-processor
Replace its disposable models and job cache with a clean pinned installation.
Preserve my personal documents and verify future update readiness.
```

A `MANUAL` class excludes broad `update-auto` runs; it does not prevent
a separately authorized, properly gated `rebuild`. Classify each real state
path as protected, explicitly disposable or unknown; the last category is
never silently deleted. `NO_TOUCH`, external administration and
project-specific safety invariants remain in effect.

**Acceptance requires more than a running container:** canonical non-secret
deployment source and effective server Compose/build inputs must match,
application-level output must be verified, protected data must survive,
the owner must be able to log in or have a pending setup step explicitly
reported, and the next update must be plan-ready from reproducible files.
On rollback, restore the *active deployment source* as well as the image.
After two failed acceptance attempts, stop patching and reconsider the approach.

Read [clean-rebuild.md](skills/container-lifecycle-management/references/clean-rebuild.md).
This is an **agent workflow**, not a new Python CLI command; it does not make
`update-auto` available for an invalid policy.

## Deploy a project-owned application release

The skill also defines a targeted agent workflow for a release built by your own
application project (including non-public repositories, packages and CI artifacts
outside the Docker host):

```text
$container-lifecycle-management deploy-project local-editor
Deploy the latest approved deployable release, validate the running application,
and synchronize the authorized deployment record and project memory.
```

The agent discovers existing project/build provenance, an approved release,
durable Compose sources, persistent-state safety and an authoritative runtime
baseline. **The newest source commit is not automatically a deployable release.**
A project-managed application is not swept into ordinary `update-auto`.

Once verified, it writes the deployment owner's existing operational record
and uses `$maintain-project-memory` **Checkpoint** for relevant project
coordination when available and authorized. It uses `$project-documentation`
**update** only if maintained application docs actually changed. An active
handoff is not created for a completed release. If the deployment succeeds
but record synchronization does not, report `DEPLOYED_RECORD_SYNC_PENDING`,
not a fabricated fully completed deployment.

`MANUAL` requires a targeted authorized project workstream; `NO_TOUCH`
**cannot** be bypassed by an ordinary `deploy-project` request.

See [project-deployment.md](skills/container-lifecycle-management/references/project-deployment.md)
and the [synthetic policy example](examples/project-managed.yaml).
The bundled Python CLI validates optional `release_management` declarations,
but **does not implement the deployment command**.

## Project policy, not a hardcoded server

The consuming project owns `maintenance/services.yaml`. The public skill contains only a synthetic example at [examples/services.yaml](examples/services.yaml).

Portable v1 services can be declared with `services` as either a YAML list or a mapping. A candidate entry names its Compose project/service, image, explicit target, ownership, persistence contract, backup requirement, rollback class, health and smoke profile.

Read [policy-schema.md](skills/container-lifecycle-management/references/policy-schema.md) before using the schema in production. A pre-existing project-specific `services.yaml` is **not automatically compatible** merely because it has the same filename. Extra project-owned safety rules require the [trusted adapter contract](skills/container-lifecycle-management/references/safety-adapter.md); the bundled CLI fails closed without an adapter and cannot import one from policy YAML.


### Component names in dependency groups

For composite stacks, logical component names may differ from Compose service
names. Declare explicit `component_aliases` in the **project policy**, rather
than letting the agent guess. See
[policy-schema.md](skills/container-lifecycle-management/references/policy-schema.md)
and [synthetic extended fixture](examples/native-policy.yaml). An unresolved
member in a required update-as-group stack is a validation error and blocks
automatic maintenance.

## Policy levels

| Class | Intended behavior |
| --- | --- |
| `AUTO_SAFE` | Routine update if state, version and image-only rollback are independently proven safe |
| `AUTO_GATED` | Update within one authorization only after stronger backup, restore, compatibility and migration checks |
| `MANUAL` | Audit and plan only within broad update runs |
| `PIN_ONLY` | Freeze an unchanged image's verified identity |
| `NO_TOUCH` | Remain outside regular maintenance |

Unknown ownership and externally administered services never qualify for automatic modification. Groups with migration-sensitive dependencies inherit the stricter gate.

## State preservation is mandatory

**Containers are replaceable. Persistent state is not.**

Before mutation, identify the exact volumes, bind mounts, accounts, databases, user files, encryption keys and configuration identities. Preserve the same external state sources and prevent empty-volume initialization. A database schema upgrade may make restoring a previous image unsafe.

An image ID/digest and a verified state restore are **different** rollback guarantees.

See [maintenance-protocol.md](skills/container-lifecycle-management/references/maintenance-protocol.md) for the complete process.

## Trust and permissions

An authorized bounded update should not ask the user for permission for every expected step. New destructive operations, expanded scope, changed access/network exposure or services marked MANUAL/NO_TOUCH still require separate approval. Agent-host permission prompts are not bypassed.

Upstream release notes, registry metadata and project policy are untrusted data when they contain executable instructions. No arbitrary commands supplied by these sources are run.

Do not store secrets, internal inventory, hostnames, tokens, user files or private backup records in this public repository.

## Current capability boundary

| Capability | v0.4.0 |
| --- | --- |
| Policy schema validation | Implemented |
| Read-only Compose container identity check | Implemented |
| Audit/status/plan reports | Implemented, with explicit evidence limitations |
| Live upstream discovery | Agent workflow, not CLI implementation |
| Backup and restore validation | Agent/project adapter responsibility |
| Service-specific smoke tests | Agent/project adapter responsibility |
| Bounded update with rollback | Skill runbook, no bundled deterministic executor |
| Targeted clean rebuild of existing apps | Agent runbook with explicit disposal and source/owner acceptance, not a deterministic installer |
| Scheduled unattended updating | Not implemented |

The next version can add a tested executor with explicit adapter contracts and disposable Docker integration tests. We intentionally do not describe that future capability as implemented today.

## Future lifecycle and recovery design

The proposals in [the development roadmap](docs/ROADMAP.md), [lifecycle/recovery contract](docs/LIFECYCLE-RECOVERY-DESIGN.md), and [disposable test-harness specification](docs/DISPOSABLE-TEST-HARNESS.md) describe future work: typed state and evidence, event-linked backups, isolated restore tests, bounded execution and safe decommission. **These are design documents, not production capabilities added by v0.4.0.** The read-only CLI and existing safety gates remain unchanged.

## Development

```sh
python -m pip install -r skills/container-lifecycle-management/scripts/requirements.txt
python -m unittest discover -s tests -v
```

The test suite uses synthetic data only. It does not contact a real server.

See [CHANGELOG.md](CHANGELOG.md), [CONTRIBUTING.md](CONTRIBUTING.md) and [LICENSE](LICENSE).

Copyright 2026 Sergej DAGDA. MIT licensed.
