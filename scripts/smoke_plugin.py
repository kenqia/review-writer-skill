#!/usr/bin/env python3
"""Cold-start the bundled v2 skill pack without network access."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from plugin_boundary import resolve_plugin_skills


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "chemical-review"


def main() -> int:
    resolution = resolve_plugin_skills(PLUGIN)
    expected = {"chemical-review-intent", "chemical-review-research", "chemical-review-synthesis", "chemical-review-qa"}
    actual = {path.name for path in resolution.skill_paths}
    if actual != expected:
        raise RuntimeError(f"unexpected v2 skill set: {sorted(actual)}")
    for skill_path in resolution.skill_paths:
        if not (skill_path / "SKILL.md").is_file():
            raise RuntimeError(f"missing cold-start skill: {skill_path}")
    with TemporaryDirectory(prefix="chemical-review-v2-smoke-") as project:
        root = Path(project)
        if list(root.iterdir()):
            raise RuntimeError("fresh smoke project is not empty")
    print("Chemical Review v2 plugin cold-start smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
