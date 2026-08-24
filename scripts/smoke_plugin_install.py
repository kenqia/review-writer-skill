#!/usr/bin/env python3
"""Install the local plugin with Codex and cold-start the installed copy."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from plugin_boundary import resolve_plugin_skills


ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = "review-writer-skill"
PLUGIN = "chemical-review"


def _run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default=shutil.which("codex") or "codex")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="chemical-review-codex-home-") as codex_home:
        env = os.environ.copy()
        env["CODEX_HOME"] = codex_home
        _run(
            [args.codex, "plugin", "marketplace", "add", str(ROOT), "--json"],
            env,
        )
        installed = _run(
            [args.codex, "plugin", "add", f"{PLUGIN}@{MARKETPLACE}", "--json"],
            env,
        )
        payload = json.loads(installed.stdout)
        installed_path = Path(payload["installedPath"])
        expected_version = json.loads(
            (ROOT / "plugins" / PLUGIN / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )["version"]
        if payload["version"] != expected_version or not installed_path.is_dir():
            raise RuntimeError(f"unexpected installed plugin payload: {payload}")
        resolution = resolve_plugin_skills(installed_path)
        if resolution.version != expected_version:
            raise RuntimeError(f"installed bundled skill version mismatch: {resolution}")
        with TemporaryDirectory(prefix="chemical-review-installed-smoke-") as project:
            intent = next(path for path in resolution.skill_paths if path.name == "chemical-review-intent")
            completed = _run(
                [
                    sys.executable,
                    str(intent / "intent.py"),
                    "init",
                    "--project",
                    project,
                    "--topic",
                    "ligand effects in nickel-mediated C-C coupling",
                ],
                env,
            )
            payload = json.loads(completed.stdout)
            if payload != {"confirmed": False, "revision": 1, "next": "human-confirmation"}:
                raise RuntimeError(f"unexpected installed Intent result: {payload}")
            if not (Path(project) / "review-brief.md").is_file():
                raise RuntimeError("installed Intent did not create review-brief.md")
    print("Installed plugin cold-start smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
