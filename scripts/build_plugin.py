#!/usr/bin/env python3
"""Synchronize the canonical Chemical Review skills into the release projection."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

try:
    from .plugin_boundary import V2_SKILL_FILES, assert_exact_files, relative_files
except ImportError:
    from plugin_boundary import V2_SKILL_FILES, assert_exact_files, relative_files


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / ".agents" / "skills"
DEST_ROOT = ROOT / "plugins" / "chemical-review" / "skills"
PLUGIN_ROOT = DEST_ROOT.parent
LICENSE_SOURCE = ROOT / "LICENSE"


def _source_files(skill: str) -> dict[str, Path]:
    source = SOURCE_ROOT / skill
    files = relative_files(source)
    assert_exact_files(files, V2_SKILL_FILES[skill], label=f"canonical {skill}")
    return files


def _sync_skill(skill: str) -> None:
    destination = DEST_ROOT / skill
    destination.mkdir(parents=True, exist_ok=True)
    current = relative_files(destination) if destination.is_dir() else {}
    source_files = _source_files(skill)
    for relative in set(current) - set(source_files):
        (destination / relative).unlink()
    for relative, path in source_files.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        shutil.copymode(path, target)


def sync() -> None:
    if not LICENSE_SOURCE.is_file():
        raise FileNotFoundError(f"project license does not exist: {LICENSE_SOURCE}")
    for skill in V2_SKILL_FILES:
        _sync_skill(skill)
    (PLUGIN_ROOT / "LICENSE").write_bytes(LICENSE_SOURCE.read_bytes())


def check() -> int:
    issues: list[str] = []
    for skill in V2_SKILL_FILES:
        source_files = _source_files(skill)
        destination = DEST_ROOT / skill
        destination_files = relative_files(destination) if destination.is_dir() else {}
        expected = set(source_files)
        actual = set(destination_files)
        for missing in sorted(expected - actual):
            issues.append(f"missing generated plugin file: {skill}/{missing}")
        for extra in sorted(actual - expected):
            issues.append(f"unexpected generated plugin file: {skill}/{extra}")
        for relative, source in source_files.items():
            target = destination / relative
            if target.is_file() and target.read_bytes() != source.read_bytes():
                issues.append(f"generated plugin file differs from canonical source: {skill}/{relative}")
    if not (PLUGIN_ROOT / "LICENSE").is_file() or (PLUGIN_ROOT / "LICENSE").read_bytes() != LICENSE_SOURCE.read_bytes():
        issues.append("plugin LICENSE differs from project LICENSE")
    if issues:
        print("Plugin projection is out of sync:", file=sys.stderr)
        print("\n".join(f"- {issue}" for issue in issues), file=sys.stderr)
        return 1
    print("Plugin projection is synchronized.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        return check()
    sync()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
