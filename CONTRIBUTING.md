# Contributing

Issues and PRs are welcome. Keep the skill portable: no private infrastructure, real hostnames, secrets or project-specific service identifiers.

The canonical instructions live at `skills/container-lifecycle-management/SKILL.md`. Keep platform manifests versioned together. Update both `README.md` and `README.ru.md` when user-facing behavior changes.

Run:

```sh
python -m pip install -r skills/container-lifecycle-management/scripts/requirements.txt
python -m unittest discover -s tests -v
```

Add synthetic tests for new policy rules, especially denied operations and restoration failures. The read-only helper must remain non-mutating. A future production executor needs separate integration tests with disposable Docker projects and explicit safety review.

Submit changes through pull requests. Never commit credentials, copies of real data, container snapshots or real backup artifacts.
