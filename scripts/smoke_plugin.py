#!/usr/bin/env python3
"""Cold-start the bundled Chemical Review skill pack without network access."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from plugin_boundary import PUBLIC_SKILL_NAMES, resolve_plugin_skills


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "chemical-review"


def main() -> int:
    resolution = resolve_plugin_skills(PLUGIN)
    expected = set(PUBLIC_SKILL_NAMES)
    actual = {path.name for path in resolution.skill_paths}
    if actual != expected:
        raise RuntimeError(f"unexpected public skill set: {sorted(actual)}")
    for skill_path in resolution.skill_paths:
        if not (skill_path / "SKILL.md").is_file():
            raise RuntimeError(f"missing cold-start skill: {skill_path}")
    with TemporaryDirectory(prefix="chemical-review-smoke-") as project:
        root = Path(project)
        if list(root.iterdir()):
            raise RuntimeError("fresh smoke project is not empty")
    print("Chemical Review plugin cold-start smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
