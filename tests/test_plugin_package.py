from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.build_plugin import _source_files
from scripts.package_plugin import release_files
from scripts.plugin_boundary import V2_SKILL_NAMES, V2_SKILL_FILES, expected_release_files, resolve_plugin_skills


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins" / "chemical-review"
BUILD_SCRIPT = ROOT / "scripts" / "build_plugin.py"
VALIDATOR = ROOT / "scripts" / "validate_plugin_package.py"


class ChemicalReviewPluginTests(unittest.TestCase):
    def test_v2_manifest_and_explicit_skill_pack(self):
        manifest = json.loads((PLUGIN_DIR / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "chemical-review")
        self.assertEqual(manifest["version"], "0.2.0-beta.1")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertIn("chemical-review-intent", " ".join(manifest["interface"]["defaultPrompt"]))
        self.assertEqual(set(V2_SKILL_NAMES), {path.name for path in resolve_plugin_skills(PLUGIN_DIR).skill_paths})

    def test_projection_is_synchronized_and_contains_only_v2_files(self):
        completed = subprocess.run([sys.executable, str(BUILD_SCRIPT), "--check"], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual({relative for _, relative in release_files(PLUGIN_DIR)}, expected_release_files())
        for skill in V2_SKILL_NAMES:
            self.assertEqual(set(_source_files(skill)), set(V2_SKILL_FILES[skill]))

    def test_package_validator_and_cold_smoke_pass(self):
        completed = subprocess.run([sys.executable, str(VALIDATOR), str(PLUGIN_DIR)], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        smoke = subprocess.run([sys.executable, str(ROOT / "scripts" / "smoke_plugin.py")], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(smoke.returncode, 0, smoke.stdout + smoke.stderr)

    def test_resolution_fails_closed_when_any_v2_skill_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            plugin = Path(temporary)
            (plugin / ".codex-plugin").mkdir()
            (plugin / ".codex-plugin" / "plugin.json").write_text(json.dumps({"name": "chemical-review", "version": "0.2.0-beta.1", "skills": "./skills/"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "HUMAN_ACTION_REQUIRED.*v2 skill"):
                resolve_plugin_skills(plugin)


if __name__ == "__main__":
    unittest.main()
