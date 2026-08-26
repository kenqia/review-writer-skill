#!/usr/bin/env python3
"""Validate the Chemical Review plugin boundary without dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

try:
    from .plugin_boundary import V2_SKILL_FILES, expected_release_files, relative_files
except ImportError:
    from plugin_boundary import V2_SKILL_FILES, expected_release_files, relative_files


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "chemical-review"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


def validate(plugin: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = plugin / ".codex-plugin" / "plugin.json"
    if not manifest_path.is_file():
        return ["missing .codex-plugin/plugin.json"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read plugin manifest: {exc}"]
    if manifest.get("name") != "chemical-review":
        errors.append("manifest name must be chemical-review")
    if not isinstance(manifest.get("version"), str) or not SEMVER.fullmatch(manifest["version"]):
        errors.append("manifest version must be strict semver")
    if manifest.get("skills") != "./skills/":
        errors.append("manifest skills must be ./skills/")
    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        errors.append("manifest interface must be an object")
    else:
        for field in ("displayName", "shortDescription", "longDescription", "developerName", "category", "capabilities", "defaultPrompt"):
            if not interface.get(field):
                errors.append(f"manifest interface field {field} is required")
    files = relative_files(plugin)
    actual = set(files)
    expected = set(expected_release_files())
    for missing in sorted(expected - actual):
        errors.append(f"missing release file: {missing}")
    for extra in sorted(actual - expected):
        errors.append(f"unexpected release file: {extra}")
    for skill, required in V2_SKILL_FILES.items():
        skill_root = plugin / "skills" / skill
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8", errors="replace") if (skill_root / "SKILL.md").is_file() else ""
        if f"name: {skill}" not in skill_text:
            errors.append(f"missing or mismatched skill identity: {skill}")
    for path in plugin.rglob("*"):
        if path.is_symlink():
            errors.append(f"symlink is not allowed in plugin: {path.relative_to(plugin)}")
        if path.is_file() and "[TODO:" in path.read_text(encoding="utf-8", errors="replace"):
            errors.append(f"TODO marker found in plugin file: {path.relative_to(plugin)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin", nargs="?", type=Path, default=PLUGIN)
    args = parser.parse_args()
    errors = validate(args.plugin.resolve())
    if errors:
        print("Plugin package validation failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"Plugin package validation passed: {args.plugin.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
