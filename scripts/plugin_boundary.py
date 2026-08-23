"""Canonical file boundary for the Chemical Review plugin projection."""

from __future__ import annotations

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
        "orchestrator.py",
        "prototype.py",
        "references/research-tools.md",
        "research.py",
        "review.py",
        "units.py",
    }
)
PLUGIN_ROOT_FILES = frozenset({".codex-plugin/plugin.json", "LICENSE", "README.md"})


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
