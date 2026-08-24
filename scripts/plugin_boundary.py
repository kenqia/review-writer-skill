"""Canonical file boundary for the Chemical Review plugin projection."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


# This is deliberately a list of runtime files, not an extension-based rule.
# Adding a new runtime asset requires an explicit review of the release
# boundary and a change here.
RUNTIME_SKILL_FILES = frozenset(
    {
        "SKILL.md",
        "WORKFLOW.md",
        "ASSET-TEMPLATES.md",
        "agents/openai.yaml",
        "feedback.py",
        "delivery.py",
        "orchestrator.py",
        "prototype.py",
        "references/research-tools.md",
        "research.py",
        "review.py",
        "units.py",
    }
)
PLUGIN_ROOT_FILES = frozenset({".codex-plugin/plugin.json", "LICENSE", "README.md"})


def _resolution_error(message: str) -> ValueError:
    return ValueError("HUMAN_ACTION_REQUIRED: " + message)


@dataclass(frozen=True)
class PluginSkillResolution:
    """Non-sensitive identity for one resolved bundled skill."""

    plugin_id: str
    version: str
    skill_path: Path


def resolve_plugin_skill(plugin_root: Path) -> PluginSkillResolution:
    """Resolve exactly the skill declared by one plugin manifest.

    The package boundary must never guess a global fallback. A missing or
    mismatched bundled skill is an installation error that callers surface to
    the user before executing a different workflow.
    """

    root = plugin_root.resolve()
    manifest_path = root / ".codex-plugin" / "plugin.json"
    if not manifest_path.is_file():
        raise _resolution_error("plugin manifest is missing; reinstall the Chemical Review plugin")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _resolution_error("plugin manifest is unreadable; reinstall the Chemical Review plugin") from error
    plugin_id = str(manifest.get("name", "")).strip()
    version = str(manifest.get("version", "")).strip()
    skills_value = str(manifest.get("skills", "")).strip()
    if plugin_id != "chemical-review" or not version or not skills_value:
        raise _resolution_error(
            "plugin manifest does not identify the Chemical Review bundled skill"
        )
    skills_root = (root / skills_value).resolve()
    try:
        skills_root.relative_to(root)
    except ValueError as error:
        raise _resolution_error("plugin skills path escapes the plugin root") from error
    skill_path = skills_root / plugin_id
    skill_file = skill_path / "SKILL.md"
    if not skill_file.is_file():
        raise _resolution_error(
            "Chemical Review bundled skill is missing; reinstall the plugin or choose the verified source"
        )
    skill_text = skill_file.read_text(encoding="utf-8")
    if "name: chemical-review" not in skill_text:
        raise _resolution_error(
            "Chemical Review bundled skill identity does not match its manifest"
        )
    return PluginSkillResolution(
        plugin_id=plugin_id,
        version=version,
        skill_path=skill_path,
    )


def relative_files(root: Path) -> dict[str, Path]:
    """Return all regular files under ``root`` keyed by POSIX path."""
    if not root.is_dir():
        raise FileNotFoundError(f"directory does not exist: {root}")
    files: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ValueError(f"symlinks are not allowed: {relative}")
        if path.is_file():
            files[relative] = path
    return files


def assert_exact_files(files: dict[str, Path], expected: frozenset[str], *, label: str) -> None:
    """Fail closed when a source or release tree contains an unknown file."""
    actual = set(files)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing {label} files: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected {label} files: {', '.join(unexpected)}")
        raise ValueError("; ".join(details))
