"""Fail-closed source and release boundary for Chemical Review v2."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


V2_SKILL_NAMES = (
    "chemical-review-intent",
    "chemical-review-research",
    "chemical-review-synthesis",
    "chemical-review-qa",
)
V2_SKILL_FILES = {
    "chemical-review-intent": frozenset({
        "SKILL.md",
        "grilling.md",
        "domain-modeling.md",
        "brief-contract.md",
        "result-and-revision.md",
        "expert-review.md",
        "agents/openai.yaml",
    }),
    "chemical-review-research": frozenset({
        "SKILL.md", "preflight.md", "discovery-and-screening.md", "candidate-acceptance.md", "full-text-and-resume.md", "evidence-and-handoff.md",
        "agents/openai.yaml",
    }),
    "chemical-review-synthesis": frozenset({
        "SKILL.md", "planning.md", "drafting.md", "handoff.md", "agents/openai.yaml",
    }),
    "chemical-review-qa": frozenset({
        "SKILL.md", "reviewers.md", "arbiter.md", "revision-routing.md", "agents/openai.yaml",
    }),
}
RUNTIME_SKILL_FILES = frozenset(
    f"skills/{skill}/{relative}"
    for skill, files in V2_SKILL_FILES.items()
    for relative in files
)
PLUGIN_ROOT_FILES = frozenset({".codex-plugin/plugin.json", "LICENSE", "README.md"})


def _resolution_error(message: str) -> ValueError:
    return ValueError("HUMAN_ACTION_REQUIRED: " + message)


@dataclass(frozen=True)
class PluginSkillResolution:
    plugin_id: str
    version: str
    skill_path: Path
    skill_paths: tuple[Path, ...]


def resolve_plugin_skills(plugin_root: Path) -> PluginSkillResolution:
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
    if plugin_id != "chemical-review" or not version or skills_value != "./skills/":
        raise _resolution_error("plugin manifest does not identify the Chemical Review v2 skill pack")
    skills_root = (root / skills_value).resolve()
    try:
        skills_root.relative_to(root)
    except ValueError as error:
        raise _resolution_error("plugin skills path escapes the plugin root") from error
    paths: list[Path] = []
    for skill_name in V2_SKILL_NAMES:
        skill_path = skills_root / skill_name
        skill_file = skill_path / "SKILL.md"
        if not skill_file.is_file():
            raise _resolution_error(f"bundled v2 skill is missing: {skill_name}")
        if f"name: {skill_name}" not in skill_file.read_text(encoding="utf-8"):
            raise _resolution_error(f"bundled skill identity does not match: {skill_name}")
        paths.append(skill_path)
    return PluginSkillResolution(plugin_id, version, skills_root, tuple(paths))


def resolve_plugin_skill(plugin_root: Path) -> PluginSkillResolution:
    """Compatibility spelling that now resolves the complete v2 pack."""
    return resolve_plugin_skills(plugin_root)


def relative_files(root: Path) -> dict[str, Path]:
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


def expected_release_files() -> frozenset[str]:
    return PLUGIN_ROOT_FILES | RUNTIME_SKILL_FILES
