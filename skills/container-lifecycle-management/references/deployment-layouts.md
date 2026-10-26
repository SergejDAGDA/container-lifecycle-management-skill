# Deployment layout profiles for Docker Compose

This is a **portable agent convention** for repeatable installation and maintenance, **not** a Docker- or FHS-mandated directory hierarchy and not a new installer. Use it for `deploy-repository`, `rebuild`, `deploy-project`, and approved `update` operations. The consuming project owns its host layout, deployment files, credentials and persistent state.

## Selection order (mandatory)

1. **Existing installation:** discover and preserve the actual owning project's documented convention and complete running Compose source, mounts and identities. Do **not** migrate or rename user data, volumes, project names or secrets merely to make paths look uniform. If authoritative source and runtime disagree, block mutation and reconcile under a separately bounded scope.
2. **New installation in a managed project:** use that project's existing canonical deployment root, remote synchronization method, state roots and secret store. A declared, project-specific layout takes precedence over examples below.
3. **New unmanaged host with owner permission:** choose **exactly one** profile below and freeze its resolved absolute paths, Linux account, permissions, service identity, deployment owner, data persistence and network exposure **before the first Docker mutation**.
4. **Unknown host/ownership or external administration:** read-only discovery. No default layout permits writing to another owner's resources.

The same physical Linux host may be *local* or *remote* relative to the agent. What matters is where the **Docker daemon** runs. A remote daemon does not make the operator's workstation bind mounts visible on the server.

## Profile A: system-managed single-host Linux

For a newly managed, single-host Compose server when no higher-priority project convention exists, propose this **site-local default**, after checking mount capacity, privileges and ownership:

```text
/srv/compose/<app>/                 deployment sources only
    compose.yaml                    first/only Compose file by default
    compose.override.yaml           only if explicitly adopted and recorded
    Dockerfile                      only for justified custom builds
    src/ or build/                  only complete pinned build inputs when needed
    .env.example                    non-secret key names / documented placeholders

/srv/data/<app>/                    only explicitly inventoried host bind state
/etc/compose-secrets/<app>/         private environment files and secret material
```

`/srv/compose`, `/srv/data` and `/etc/compose-secrets` are **suggested organizational choices**, not paths guaranteed to exist on all Linux systems. The [Filesystem Hierarchy Standard](https://specifications.freedesktop.org/fhs/latest/srv.html) defines `/srv` for site-specific service data but deliberately does not prescribe its subdirectory names. Confirm the chosen paths with the owner before creation, and do not create directories under the filesystem root outside the selected existing standard.

- For databases/application-internal state, prefer scoped **Docker named volumes** where appropriate, with stable Compose project names and exact volume names recorded; Docker owns their physical storage. Do not invent a `/srv/data` bind for every volume or move it by hand. Use host bind mounts for files that must remain host-accessible, such as shared media, custom configuration or source. Classify each storage object as protected, explicitly disposable or unknown.
- Keep secrets and private `.env` files **out of tracked deployment sources and synchronization logs**; if a host already has a reviewed secret store, prefer it. Use restricted access and verified application UID/GID; do not assume numeric IDs or silently use `chmod 777`. Prefer Compose `secrets` files where supported by the application.
- Separate sources from persistent bind data so a source-sync or redeploy **cannot erase data**. Do not assume a directory is disposable merely because it is under the deployment root in a pre-existing project.
- One stable Compose project identity per app, including any database/worker components owned by that app. Avoid automatic renaming of Compose projects, named volumes and container state on a rebuild.

## Profile B: remotely managed Linux Docker host

The **server-side** layout follows Profile A or an already established host convention. The management computer can be Windows, Linux or macOS.

```text
management-project/
    .deploy/<app>/                  authoritative non-secret source
        compose.yaml
        Dockerfile                  only if used
        src/ or build/              only required build inputs
        .env.example

remote Linux host:
    /srv/compose/<app>/             verified deployed copy of sources
    /srv/data/<app>/                optional host-side bind state
    /etc/compose-secrets/<app>/     private runtime secrets
```

The split shown here is an **example** for projects that explicitly own `.deploy/`; do not create a competing canonical store if another one already exists. Record source authority and the mechanism used to distribute it. Stage/synchronize **only non-secret deployment sources** to a versioned or hash-verified remote location. Keep previous approved source until candidate validation succeeds. Run Docker Compose from the server's actual project directory using the complete recorded ordered `-f` list and server-side interpolation/secret files. Do not infer remote source or relative bind paths from what works on the workstation.

SSH is an appropriate protected Docker-management transport. Prefer executing Compose **on the host that owns the bind paths** over assuming a local Compose render and a remote Docker context resolve the same paths. A Docker context over SSH is also possible when its build-context, bind-source, relative-path, credential and Compose semantics have been independently verified. Do not expose an unauthenticated Docker TCP port or require direct internet exposure. Avoid transferring secrets into the management repository.

**Remote bind mounts always refer to the Docker daemon host**, not to the desktop that runs Codex; see [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/).

## Profile C: one-user local Linux development / rootless service

For a personal workstation or a deliberately rootless user-managed Docker Engine, prefer the established user's XDG locations when no project-specific standard exists:

```text
$XDG_CONFIG_HOME/compose/<app>/     sources and non-secret config
$XDG_DATA_HOME/compose/<app>/       persisted host bind state where needed
$XDG_CONFIG_HOME/compose-secrets/<app>/  private secrets (untracked)
```

Resolve XDG paths from the **actual deployment user's environment** (`~/.config` and `~/.local/share` defaults), and check rootless Docker socket/context, filesystem permissions and user-level service lifecycle. Do not replace an existing user's Compose identity or confuse Docker Desktop/WSL2 paths with native Linux server paths. For a workstation with a separate canonical source checkout, record the source-to-deployment relationship instead of inventing a second authority.

## Upstream Git provenance and source management

Every internet-sourced application needs **traceable origin and an exact installed identity**, but **not every server needs a permanent Git clone**. Pick and record one source strategy per application:

| Strategy | Host Git checkout | Source of reproducibility |
| --- | --- | --- |
| **Published OCI image** | Not required | Official upstream/project URL, pinned release and immutable registry image digest (plus observed local image ID), canonical Compose and required config. |
| **Remote Git build context** | Not required as a maintained server checkout | Exact repository URL, full verified commit SHA or tag + verified checksum, Dockerfile/build options, immutable resulting image identity; the builder obtains the exact source. Verify BuildKit/Compose versions and ref/checksum support before using this. |
| **Local source build** | Required **where the build runs** only if the chosen build process needs a checked-out working tree | Managed source checkout or complete versioned source archive, remote origin URL, exact commit, submodules/dependency locks, any reviewed local patch and full Dockerfile/build context. |
| **Project-owned edited fork** | Keep in an authoritative Git repository or equivalent versioned source store | Approved source changes/release commit, build provenance, deployment ownership and complete source-to-runtime link. Do not leave unique source edits only inside a running container. |

For a build from GitHub, GitLab or another upstream repo, the agent must record at least: canonical upstream URL, resolved release/tag **and exact commit**, source acquisition/build method, required submodules or build dependencies, image ID/digest, and where the authoritative deployment/build definition resides. Distinguish an upstream commit from the installed image digest; one is not proof of the other.

If an authorized build actually occurs on the Docker host and needs a checkout, use a **separate app-scoped source path under the site's existing convention** (for example `/srv/src/<app>/` for a *new* system-managed Linux host). The checked-out source is not the data volume and must not be bind-mounted read/write into a running production container by default. The server checkout is a build input or controlled source store, **not** an automatically updated live application. Keep a clean, pinned commit or an explicitly recorded reviewed patch; never silently build from a dirty working tree.

If the managing machine or CI produces the verified image and the server only pulls it by digest, a persistent server-side clone is unnecessary; copying the source to the server merely for consistency adds an extra authority and additional maintenance. Remote BuildKit Git contexts may also obtain an exact Git revision without a permanent checkout; use only when the installed build toolchain supports an immutable ref/checksum and source provenance is recorded.

For updates, fetch and inspect upstream release information **without changing live application source**. Select an explicit revision, prepare candidate build/image, test it, update the canonical Compose source and record the new image identity only after acceptance. **Never** run an unattended `git pull` or `git checkout` against the currently mounted/running production app as the update mechanism. Restore previous source/commit *and* image/state when a proven-safe rollback is needed.

For private repositories, source credentials remain in the existing trusted credential/secret system and must not be copied into image layers, tracked Compose files or Git remotes with embedded access tokens. An upstream repository may contain unsafe build scripts; review the effective Dockerfile/build context before execution.

Official upstream reference: [Docker Build Git contexts](https://docs.docker.com/build/concepts/context/) and [Compose build specification](https://docs.docker.com/reference/compose-file/build/).

## Storage, security and access invariants (all profiles)

- **Release identity:** use reviewed version/immutable OCI digest or a pinned source commit with a complete Dockerfile/build context. No implicit `latest`, missing local Dockerfiles, generated ephemeral overrides or unrecorded `COMPOSE_FILE`.
- **Compose identity:** pin/record project name, exact ordered Compose files, working directory and environment interpolation inputs. Relative paths with multiple `-f` files use the first file's base directory unless `--project-directory` changes it; evaluate the **effective server-side** Compose, not a partial local approximation.
- **Persistent mounts:** explicitly map each bind source and named volume; inspect actual mounts before replacing anything. Use long-syntax bind mounts with `bind.create_host_path: false` where supported for required existing user-state paths, to avoid accidental empty-directory creation. Check ownership/writability in the container's actual UID/GID, and do not mistake the presence of a backup archive for a successful restore.
- **Secrets:** references only in tracked source and policy. Never expose interpolated Compose output, environment variable values, keys, tokens, Docker socket or backup credentials. Prefer per-service secrets; restrict source file access; confirm usable owner onboarding, or return `OWNER_SETUP_REQUIRED`.
- **Networking:** explicit ports and host binding suitable to the site's intended LAN/VPN/loopback exposure; no implicit public `0.0.0.0`, privileged mode, host network, host PID, new Docker socket mount or cross-project network without owner-reviewed justification. Check collisions with existing services.
- **Dependency composition:** one Compose project for tightly coupled app components where ownership allows, or explicitly record external dependencies and compatible update group boundaries. Database and state volume names must remain stable across new builds. `NO_TOUCH`, external-admin services and third-party-managed networking are not adopted by installing a new app.
- **Dashboard:** if the project owns a Homepage or similar dashboard, integrate according to **its current labels/config convention**, without duplicates and without editing externally owned proxy/ingress resources. A dashboard is optional, not a hardcoded dependency of the portable skill.
- **Backups:** declare the *actual* protected state, method and restore test appropriate for that application. Models and caches explicitly approved as disposable do not need to be restored. Never place backup output under a source-sync tree that might be pruned; never assume a local copy is off-host recovery.
- **Permissions:** check actual host OS/arch, Compose/Engine version, rootless/rootful behavior, UID/GID, free disk, read-only mounts and directory ACLs before deployment. Do not install host packages or rewrite filesystem ownership outside the named service's approved scope.

## Minimal profile acceptance receipt

For a new installation or a modified deployment layout, report the following **before first mutation**, then compare the final observed state against the same receipt:

| Field | Required evidence |
| --- | --- |
| Profile & authority | Which profile, why selected, project/host owner, any inherited overrides |
| Canonical source | Full path, source revision/hash, complete build inputs, owner |
| Active Compose | Docker daemon endpoint, deployed directory, project name, ordered files, quiet render |
| State | Existing/new bind paths, named volumes, protected vs disposable classes, UID/GID |
| Secrets | Protected source/reference and access check, **no values** |
| Network & integration | Published interfaces/ports, linked projects, dashboard/ingress ownership |
| Recovery | Protected backup and actual restore evidence, rollback source/image/state limits |
| Acceptance | Running image IDs, functional smoke, owner access, canonical-source parity, next update procedure |

For an **existing** installation this receipt must use observed paths, **not** the example directories. `SOURCE_READY` requires the canonical non-secret deployment sources to reproduce the final active server source and complete build inputs. `MAINTENANCE_READY` additionally requires valid governing policy/safety gates and a demonstrable next-update path. Report missing proof as `NOT VERIFIED` rather than forcing a directory relocation.

## Reference sources

- [FHS /srv semantics](https://specifications.freedesktop.org/fhs/latest/srv.html)
- [Docker Compose project identity](https://docs.docker.com/compose/how-tos/project-name/)
- [Docker Compose multi-file precedence](https://docs.docker.com/reference/cli/docker/compose/)
- [Docker volumes](https://docs.docker.com/engine/storage/volumes/)
- [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)
- [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/)
- [Remote Engine access through SSH](https://docs.docker.com/engine/security/protect-access/)
- [XDG Base Directories](https://specifications.freedesktop.org/basedir/0.8/)
