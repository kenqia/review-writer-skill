#!/usr/bin/env python3
"""Create a deterministic Chemical Review plugin archive and checksum."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "chemical-review"

# Keep the release boundary intentionally explicit.  Adding a new plugin
# component should require an intentional change here rather than silently
# shipping whatever happens to be present in the working tree.
ALLOWED_FILES = frozenset({
    ".codex-plugin/plugin.json",
    "LICENSE",
    "README.md",
})
ALLOWED_PREFIXES = ("skills/chemical-review/",)
ALLOWED_SKILL_SUFFIXES = frozenset({".json", ".md", ".py", ".yaml", ".yml"})
DENIED_COMPONENTS = frozenset({
    ".git",
    ".playwright-mcp",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
})
DENIED_FILENAMES = frozenset({
    ".env",
    "CONTEXT.md",
    "auth.json",
    "cookies.json",
    "credentials.json",
    "secrets.json",
    "session.json",
})
DENIED_SUFFIXES = frozenset({
    ".db",
    ".har",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
})


def _is_allowed(relative: str) -> bool:
    if relative in ALLOWED_FILES:
        return True
    return any(relative.startswith(prefix) for prefix in ALLOWED_PREFIXES) and (
        Path(relative).suffix.lower() in ALLOWED_SKILL_SUFFIXES
    )


def _is_denied(relative_path: Path) -> bool:
    if any(component in DENIED_COMPONENTS for component in relative_path.parts):
        return True
    if relative_path.name in DENIED_FILENAMES or relative_path.name.startswith(".env."):
        return True
    return relative_path.suffix.lower() in DENIED_SUFFIXES


def release_files(plugin: Path = PLUGIN) -> Iterator[tuple[Path, str]]:
    """Yield release files after enforcing the plugin package boundary.

    The function fails closed: unknown files, symlinks, and known secret or
    development artefacts are errors, not silently skipped entries.
    """
    if not plugin.is_dir():
        raise FileNotFoundError(f"plugin directory does not exist: {plugin}")
    for path in sorted(plugin.rglob("*")):
        relative_path = path.relative_to(plugin)
        relative = relative_path.as_posix()
        if path.is_symlink():
            raise ValueError(f"symlinks are not allowed in release package: {relative}")
        if not path.is_file():
            continue
        if _is_denied(relative_path):
            raise ValueError(f"denied file in release package: {relative}")
        if not _is_allowed(relative):
            raise ValueError(f"file is outside release allowlist: {relative}")
        yield path, relative


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
