from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.build_plugin import _files
from scripts.package_plugin import release_files
from scripts.plugin_boundary import RUNTIME_SKILL_FILES, resolve_plugin_skill


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins" / "chemical-review"
PLUGIN_SKILL_DIR = PLUGIN_DIR / "skills" / "chemical-review"
BUILD_SCRIPT = ROOT / "scripts" / "build_plugin.py"
PLUGIN_VALIDATOR = ROOT / "scripts" / "validate_plugin_package.py"


class ChemicalReviewPluginTests(unittest.TestCase):
    def test_plugin_manifest_is_release_ready_and_points_to_bundled_skill(self):
        manifest_path = PLUGIN_DIR / ".codex-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "chemical-review")
        self.assertEqual(manifest["version"], "0.1.0-beta.1")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(manifest["interface"]["displayName"], "Chemical Review")
        self.assertTrue((PLUGIN_DIR / "README.md").is_file())
        self.assertEqual(
            (PLUGIN_DIR / "LICENSE").read_bytes(),
            (ROOT / "LICENSE").read_bytes(),
        )

    def test_plugin_skill_is_generated_from_canonical_project_skill(self):
        completed = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertTrue((PLUGIN_SKILL_DIR / "SKILL.md").is_file())
        self.assertTrue((PLUGIN_SKILL_DIR / "orchestrator.py").is_file())
        metadata = (PLUGIN_SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("default_prompt:", metadata)

    def test_plugin_manifest_passes_repository_plugin_validator(self):
        completed = subprocess.run(
            [sys.executable, str(PLUGIN_VALIDATOR), str(PLUGIN_DIR)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_plugin_resolution_reports_bundled_skill_identity(self):
        resolution = resolve_plugin_skill(PLUGIN_DIR)

        self.assertEqual(resolution.plugin_id, "chemical-review")
        self.assertEqual(resolution.version, "0.1.0-beta.1")
        self.assertEqual(
            resolution.skill_path,
            PLUGIN_DIR / "skills" / "chemical-review",
        )

    def test_plugin_resolution_fails_closed_when_skill_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            plugin = Path(temporary)
            (plugin / ".codex-plugin").mkdir()
            (plugin / ".codex-plugin" / "plugin.json").write_text(
                json.dumps({"name": "chemical-review", "version": "0.1.0-beta.1", "skills": "./skills/"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "HUMAN_ACTION_REQUIRED.*bundled skill"):
                resolve_plugin_skill(plugin)

    def test_release_file_allowlist_is_explicit(self):
        files = {relative for _, relative in release_files(PLUGIN_DIR)}
        self.assertIn(".codex-plugin/plugin.json", files)
        self.assertIn("README.md", files)
        self.assertIn("LICENSE", files)
        self.assertTrue(any(path.startswith("skills/chemical-review/") for path in files))

    def test_release_file_allowlist_rejects_development_or_secret_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            plugin = Path(temporary)
            (plugin / ".codex-plugin").mkdir()
            (plugin / "skills" / "chemical-review").mkdir(parents=True)
            for relative in (".codex-plugin/plugin.json", "README.md", "LICENSE"):
                (plugin / relative).parent.mkdir(parents=True, exist_ok=True)
                (plugin / relative).write_text("ok", encoding="utf-8")
            (plugin / "skills" / "chemical-review" / "SKILL.md").write_text("ok", encoding="utf-8")
            (plugin / ".env").write_text("SECRET=redacted", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unexpected release files"):
                list(release_files(plugin))

    def test_release_file_allowlist_rejects_unknown_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            plugin = Path(temporary)
            (plugin / ".codex-plugin").mkdir()
            (plugin / "skills" / "chemical-review").mkdir(parents=True)
            for relative in (".codex-plugin/plugin.json", "README.md", "LICENSE"):
                (plugin / relative).parent.mkdir(parents=True, exist_ok=True)
                (plugin / relative).write_text("ok", encoding="utf-8")
            (plugin / "skills" / "chemical-review" / "SKILL.md").write_text("ok", encoding="utf-8")
            (plugin / "notes.txt").write_text("development note", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unexpected release files"):
                list(release_files(plugin))

    def test_canonical_projection_rejects_unknown_runtime_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            for relative in RUNTIME_SKILL_FILES:
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("ok", encoding="utf-8")
            (source / "credentials.yaml").write_text("secret", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unexpected canonical runtime files"):
                _files(source)


if __name__ == "__main__":
    unittest.main()
