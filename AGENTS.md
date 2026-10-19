# Repository Guidance

Canonical Agent Skill: `skills/container-lifecycle-management/SKILL.md`.

Portable behavior belongs in that skill and its references. Service addresses, project-specific paths and live host details belong only in the consuming project's policy.

Keep English and Russian public documentation consistent. Update `plugin.json`, `.claude-plugin/plugin.json` and `CHANGELOG.md` together whenever changing the public version.

Never add private credentials, host-specific inventory or production snapshots to this public repository. Tests must use synthetic fixtures and must never require a production Docker daemon.

Project-owned deployment workflows may coordinate existing project-memory and documentation skills, but must respect each project's ownership and write policy. Do not create parallel handoff systems or silently treat the latest Git commit as an approved release.

The read-only Python tool is not an update executor. Do not claim otherwise.
