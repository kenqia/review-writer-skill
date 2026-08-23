#!/usr/bin/env python3
"""Synchronize the canonical project skill into the Chemical Review plugin.

The project-scoped skill is the only editable source. The plugin copy is a
release-facing projection that is checked into the repository so marketplace
and release tooling can inspect it, but it must never be edited by hand.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

try:
    from .plugin_boundary import RUNTIME_SKILL_FILES, assert_exact_files, relative_files
except ImportError:  # Direct execution: ``python scripts/build_plugin.py``.
    from plugin_boundary import RUNTIME_SKILL_FILES, assert_exact_files, relative_files


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".agents" / "skills" / "chemical-review"
DEST = ROOT / "plugins" / "chemical-review" / "skills" / "chemical-review"
PLUGIN_ROOT = DEST.parents[1]
LICENSE_SOURCE = ROOT / "LICENSE"
LICENSE_DEST = PLUGIN_ROOT / "LICENSE"


def _files(root: Path) -> dict[Path, bytes]:
    paths = relative_files(root)
    assert_exact_files(
        paths,
        RUNTIME_SKILL_FILES,
        label="canonical runtime",
    )
    result: dict[Path, bytes] = {}
    for relative, path in paths.items():
        result[Path(relative)] = path.read_bytes()
    if Path("SKILL.md") not in result:
        raise ValueError("canonical skill is missing SKILL.md")
    return result


def _check(source_files: dict[Path, bytes], destination_files: dict[Path, bytes]) -> list[str]:
    issues: list[str] = []
    source_paths = set(source_files)
    destination_paths = set(destination_files)
    for path in sorted(source_paths - destination_paths):
        issues.append(f"missing generated plugin file: {path}")
    for path in sorted(destination_paths - source_paths):
        issues.append(f"unexpected generated plugin file: {path}")
    for path in sorted(source_paths & destination_paths):
        if source_files[path] != destination_files[path]:
            issues.append(f"generated plugin file differs from canonical source: {path}")
    return issues


def sync() -> None:
    source_files = _files(SOURCE)
    if not LICENSE_SOURCE.is_file():
        raise FileNotFoundError(f"project license does not exist: {LICENSE_SOURCE}")
    destination_files = _files(DEST) if DEST.is_dir() and (DEST / "SKILL.md").is_file() else {}
    DEST.mkdir(parents=True, exist_ok=True)
    for path in sorted(set(destination_files) - set(source_files)):
        (DEST / path).unlink()
    for path, content in source_files.items():
        target = DEST / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        shutil.copymode(SOURCE / path, target)
    LICENSE_DEST.write_bytes(LICENSE_SOURCE.read_bytes())
    shutil.copymode(LICENSE_SOURCE, LICENSE_DEST)


def check() -> int:
    source_files = _files(SOURCE)
    destination_files = (
        _files(DEST)
        if DEST.is_dir() and (DEST / "SKILL.md").is_file()
        else {}
    )
    issues = _check(source_files, destination_files)
    if not LICENSE_DEST.is_file():
        issues.append("plugin is missing the project LICENSE")
    elif LICENSE_DEST.read_bytes() != LICENSE_SOURCE.read_bytes():
        issues.append("plugin LICENSE differs from the project LICENSE")
    if issues:
        print("Plugin projection is out of sync:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    print("Plugin projection is synchronized.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the projection differs")
    args = parser.parse_args()
    if args.check:
        return check()
    sync()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
