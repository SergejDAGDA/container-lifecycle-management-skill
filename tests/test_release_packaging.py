"""Current package version and historical published release checks."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "container-lifecycle-management"
VERSION = "0.6.0"


class PublicReleasePackagingTests(unittest.TestCase):
    def test_installable_skill_and_plugin_versions_match(self):
        for manifest in ("plugin.json", ".claude-plugin/plugin.json"):
            self.assertEqual(json.loads((ROOT / manifest).read_text(encoding="utf-8"))["version"], VERSION)
        self.assertEqual((SKILL / "VERSION").read_text(encoding="utf-8").strip(), VERSION)
        for path in ("SKILL.md", "scripts/maintenance.py", "scripts/doctor.py",
                     "scripts/compose_preflight.py", "references/policy-schema.md",
                     "references/maintenance-protocol.md"):
            self.assertTrue((SKILL / path).is_file(), path)

    def test_repository_identity_metadata_and_compatibility_contract(self):
        canonical = "https://github.com/SergejDAGDA/container-lifecycle-management-skill"
        native = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        claude = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        market = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(market["name"], "container-lifecycle-management-skill")
        self.assertEqual(market["plugins"][0]["source"]["url"], canonical + ".git")
        self.assertEqual(native["name"], "container-lifecycle-management")
        self.assertEqual(claude["name"], "container-lifecycle-management")
        self.assertEqual(market["plugins"][0]["name"], "container-lifecycle-management")
        for manifest in (native, claude):
            self.assertEqual(manifest["repository"], canonical)
            self.assertEqual(manifest["homepage"], canonical)
        self.assertIn(
            'API = "maintain-server-containers/safety-adapter/v1"',
            (SKILL / "scripts/safety_adapter.py").read_text(encoding="utf-8"),
        )

    def test_skill_id_migration_preserves_safety_adapter_api(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        agent = (SKILL / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: container-lifecycle-management\n"))
        self.assertIn("Use $container-lifecycle-management", agent)
        self.assertFalse((ROOT / "skills/maintain-server-containers").exists())
        adapter = (SKILL / "scripts/safety_adapter.py").read_text(encoding="utf-8")
        self.assertIn('API = "maintain-server-containers/safety-adapter/v1"', adapter)

    def test_release_notes_and_changelog_are_consistent(self):
        notes = (ROOT / "docs/releases/v0.4.0.md").read_text(encoding="utf-8")
        change = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## 0.4.0 - 2026-10-14", change)
        for term in ("PR #25", "PR #26", "read-only", "off-host",
                     "no bundled deterministic production"):
            self.assertIn(term.lower(), notes.lower())
        self.assertIn("## 0.3.0 - 2026-10-13", change)

    def test_codex_update_uses_published_tag_only(self):
        guide = (ROOT / "docs/CODEX-INSTALL-UPDATE.md").read_text(encoding="utf-8")
        self.assertIn("tree/v0.4.0/skills/maintain-server-containers", guide)
        for term in ("back up", "version", "restart", "read-only"):
            self.assertIn(term, guide.lower())
        for name in ("README.md", "README.ru.md"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("v0.4.0", source)
            self.assertIn("CODEX-INSTALL-UPDATE.md", source)

    def test_publication_is_separate_manual_action(self):
        notes = (ROOT / "docs/releases/v0.4.0.md").read_text(encoding="utf-8")
        for item in ("manual", "exact", "Tests", "Disposable Compose",
                     "tag", "GitHub Release"):
            self.assertIn(item.lower(), notes.lower())
        for obsolete in (".github/workflows/release-v0.4.0.yml",
                         ".github/scripts/publish_v040.py",
                         "tests/test_release_publication.py"):
            self.assertFalse((ROOT / obsolete).exists(), obsolete)

    def test_v030_historical_release_remains_documented(self):
        workflow = (ROOT / ".github/workflows/release-v0.3.0.yml").read_text(encoding="utf-8")
        notes = (ROOT / "docs/releases/v0.3.0.md").read_text(encoding="utf-8")
        self.assertIn("v0.3.0", workflow)
        self.assertIn("de1708213dbaf2895719120023d5bddfe42715e3", workflow)
        self.assertIn("v0.3.0", notes)


if __name__ == "__main__":
    unittest.main()
