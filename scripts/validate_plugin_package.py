#!/usr/bin/env python3
"""Validate the repository's plugin boundary without external dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "chemical-review"
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def validate(plugin: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = plugin / ".codex-plugin" / "plugin.json"
    if not manifest_path.is_file():
        return ["missing .codex-plugin/plugin.json"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read plugin manifest: {exc}"]
    if not isinstance(manifest, dict):
        return ["plugin manifest must be a JSON object"]
    if manifest.get("name") != "chemical-review":
        errors.append("manifest name must be chemical-review")
    version = manifest.get("version")
    if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
        errors.append("manifest version must be strict semver")
    if manifest.get("license") != "MIT":
        errors.append("manifest license must be MIT")
    if manifest.get("skills") != "./skills/":
        errors.append("manifest skills must be ./skills/")
    for field in ("description", "author"):
        if not manifest.get(field):
            errors.append(f"manifest field {field} is required")
    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        errors.append("manifest interface must be an object")
    else:
        for field in ("displayName", "shortDescription", "longDescription", "developerName", "category", "capabilities", "defaultPrompt"):
            if not interface.get(field):
                errors.append(f"manifest interface field {field} is required")
    skill = plugin / "skills" / "chemical-review"
    required = ("SKILL.md", "WORKFLOW.md", "ASSET-TEMPLATES.md", "orchestrator.py", "research.py", "prototype.py", "units.py", "review.py", "feedback.py")
    for filename in required:
        if not (skill / filename).is_file():
            errors.append(f"missing bundled skill file: {filename}")
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
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Plugin package validation passed: {args.plugin.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
