#!/usr/bin/env python3
"""Cold-start the bundled plugin skill without network access."""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "chemical-review" / "skills" / "chemical-review"
sys.path.insert(0, str(SKILL))

from orchestrator import ChemicalReviewOrchestrator  # noqa: E402


def main() -> int:
    with TemporaryDirectory(prefix="chemical-review-plugin-smoke-") as project:
        root = Path(project)
        result = ChemicalReviewOrchestrator(root).start(
            "ligand effects in nickel-mediated C-C coupling"
        )
        if (result.phase, result.status) != ("GRILL", "ACTIVE"):
            raise RuntimeError(
                f"unexpected cold-start state: {result.phase}/{result.status}"
            )
        expected = {"workflow-state.md", "review-intent.md", "domain-profile.md"}
        generated = {path.name for path in root.iterdir()}
        if generated != expected:
            raise RuntimeError(f"unexpected cold-start assets: {sorted(generated)}")
    print("Plugin cold-start smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
