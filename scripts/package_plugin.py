#!/usr/bin/env python3
"""Create a deterministic Chemical Review plugin archive and checksum."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
import hashlib
import json
from pathlib import Path
import zipfile

try:
    from .plugin_boundary import (
        PLUGIN_ROOT_FILES,
        RUNTIME_SKILL_FILES,
        assert_exact_files,
        relative_files,
    )
except ImportError:  # Direct execution: ``python scripts/package_plugin.py``.
    from plugin_boundary import (
        PLUGIN_ROOT_FILES,
        RUNTIME_SKILL_FILES,
        assert_exact_files,
        relative_files,
    )


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "chemical-review"

# Keep the release boundary intentionally explicit.  Adding a new plugin
# component should require an intentional change here rather than silently
# shipping whatever happens to be present in the working tree.
ALLOWED_FILES = PLUGIN_ROOT_FILES | frozenset(
    f"skills/chemical-review/{relative}" for relative in RUNTIME_SKILL_FILES
)
def release_files(plugin: Path = PLUGIN) -> Iterator[tuple[Path, str]]:
    """Yield release files after enforcing the plugin package boundary.

    The function fails closed: unknown files, symlinks, and known secret or
    development artefacts are errors, not silently skipped entries.
    """
    files = relative_files(plugin)
    assert_exact_files(files, ALLOWED_FILES, label="release")
    for relative in sorted(files):
        yield files[relative], relative


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    manifest = json.loads(
        (PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    version = manifest["version"]
    files = list(release_files(PLUGIN))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    archive = args.output_dir / f"chemical-review-{version}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path, relative in files:
            info = zipfile.ZipInfo(f"chemical-review/{relative}")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"Packaged {archive}")
    print(f"SHA256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
