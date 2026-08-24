"""Public Intent-stage document contract for Chemical Review v2.

The Intent skill owns only ``review-brief.md`` and its human-readable revision
snapshots.  It deliberately does not import the v1 orchestrator or create a
Python payload for a later stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import re
from typing import Mapping


FIELDS = (
    ("research_question", "Research question"),
    ("core_claims", "Core-claim candidates"),
    ("scope", "Scope"),
    ("exclusions", "Exclusions"),
    ("audience", "Audience"),
    ("contribution", "Expected contribution"),
    ("evidence_standards", "Evidence standards"),
    ("boundary_scenarios", "Boundary scenarios"),
)


class ConfirmationRequired(RuntimeError):
    """A confirmed brief has a pending change and cannot be consumed yet."""


class BriefIncomplete(ValueError):
    """The researcher has not supplied all decision-relevant fields."""


@dataclass(frozen=True)
class ReviewBrief:
    topic: str
    confirmed: bool
    values: Mapping[str, str | tuple[str, ...]]
    revision: int = 1


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value[:70] or "review"


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip('"')
    return values, text[end + 5 :]


def _yaml_scalar(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return "\n".join(f"- {str(item).strip()}" for item in value)
    return str(value).strip()


class IntentStage:
    """Create, confirm, and safely revise a Markdown review brief."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.path = self.project_root / "review-brief.md"
        self.proposed_path = self.project_root / "review-brief.proposed.md"
        self.history = self.project_root / "intent-history"

    def initialize(self, topic: str, *, materials: tuple[str | Path, ...] = ()) -> ReviewBrief:
        topic = topic.strip()
        if not topic:
            raise ValueError("topic cannot be blank")
        self.project_root.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            return self.read_any()
        values: dict[str, str | tuple[str, ...]] = {
            "research_question": f"Open question: what should be explained about {topic}?",
            "core_claims": ("Open question: identify the central comparative claim.",),
            "scope": "Open question: systems, date range, and evidence boundary.",
            "exclusions": "Open question: explicitly excluded systems and claims.",
            "audience": "Open question: intended chemistry readership.",
            "contribution": "Open question: what decision or understanding should change?",
            "evidence_standards": "Open question: primary full text, locator, and comparability requirements.",
            "boundary_scenarios": "Open question: how UNKNOWN, NOT_COMPARABLE, and Chemical GAP should be handled.",
            "known_material": self._safe_materials(materials),
        }
        brief = ReviewBrief(topic=topic, confirmed=False, values=values)
        self._write(brief, next_action="Answer the open questions, then explicitly confirm this brief.")
        return brief

    def confirm(self, decisions: Mapping[str, object]) -> ReviewBrief:
        if self.proposed_path.exists():
            raise ConfirmationRequired("a proposed intent change requires confirm_change(), not a new confirmation")
        current = self.read_any()
        merged = dict(current.values)
        for key, _heading in FIELDS:
            if key in decisions:
                value = decisions[key]
                if key == "core_claims":
                    if isinstance(value, str):
                        value = tuple(item.strip() for item in value.split("\n") if item.strip())
                    elif isinstance(value, (list, tuple)):
                        value = tuple(str(item).strip() for item in value if str(item).strip())
                merged[key] = value  # type: ignore[assignment]
        missing = self._missing(merged)
        if missing:
            raise BriefIncomplete("missing decision fields: " + ", ".join(missing))
        brief = ReviewBrief(topic=current.topic, confirmed=True, values=merged, revision=current.revision + 1)
        self._snapshot(current, "before-confirm")
        self._write(brief, next_action="Research may consume this confirmed review brief.")
        if self.proposed_path.exists():
            self.proposed_path.unlink()
        return brief

    def propose_change(self, changes: Mapping[str, object]) -> ReviewBrief:
        current = self.read_any(ignore_pending=True)
        merged = dict(current.values)
        for key, value in changes.items():
            if key not in {field for field, _heading in FIELDS}:
                raise ValueError(f"unknown review-brief field: {key}")
            if key == "core_claims" and isinstance(value, str):
                value = tuple(item.strip() for item in value.split("\n") if item.strip())
            merged[key] = value  # type: ignore[assignment]
        proposal = ReviewBrief(topic=current.topic, confirmed=False, values=merged, revision=current.revision + 1)
        self._write(proposal, next_action="Human confirmation is required before downstream stages may consume this change.", path=self.proposed_path)
        return proposal

    def confirm_change(self) -> ReviewBrief:
        if not self.proposed_path.exists():
            raise ValueError("no proposed review-brief change exists")
        proposal = self._read_path(self.proposed_path)
        missing = self._missing(proposal.values)
        if missing:
            raise BriefIncomplete("proposed brief is incomplete: " + ", ".join(missing))
        current = self.read_any(ignore_pending=True)
        self._snapshot(current, "before-change")
        confirmed = ReviewBrief(proposal.topic, True, proposal.values, proposal.revision)
        self._write(confirmed, next_action="Research may consume this confirmed review brief.")
        self.proposed_path.unlink()
        return confirmed

    def read_confirmed(self) -> ReviewBrief:
        if self.proposed_path.exists():
            raise ConfirmationRequired("a proposed intent change awaits explicit confirmation")
        brief = self.read_any()
        if not brief.confirmed:
            raise ConfirmationRequired("review brief is not explicitly confirmed")
        return brief

    def read_any(self, *, ignore_pending: bool = False) -> ReviewBrief:
        if not self.path.exists():
            raise FileNotFoundError("review-brief.md does not exist")
        return self._read_path(self.path)

    def _read_path(self, path: Path) -> ReviewBrief:
        metadata, body = _frontmatter(path.read_text(encoding="utf-8"))
        topic = metadata.get("topic", "").strip()
        values: dict[str, str | tuple[str, ...]] = {}
        for key, heading in FIELDS:
            marker = f"## {heading}\n"
            start = body.find(marker)
            if start < 0:
                values[key] = ""
                continue
            start += len(marker)
            end = body.find("\n## ", start)
            raw = body[start:] if end < 0 else body[start:end]
            lines = [line.strip() for line in raw.splitlines() if line.strip()]
            if key == "core_claims":
                values[key] = tuple(line[2:].strip() if line.startswith("- ") else line for line in lines)
            else:
                values[key] = " ".join(lines)
        material_start = body.find("## Known project material\n")
        if material_start >= 0:
            material_start += len("## Known project material\n")
            material_end = body.find("\n## ", material_start)
            raw = body[material_start:] if material_end < 0 else body[material_start:material_end]
            values["known_material"] = "\n".join(line.strip() for line in raw.splitlines() if line.strip())
        else:
            values["known_material"] = ""
        return ReviewBrief(topic, metadata.get("confirmed", "false").lower() == "true", values, int(metadata.get("revision", "1")))

    @staticmethod
    def _missing(values: Mapping[str, object]) -> list[str]:
        missing: list[str] = []
        for key, heading in FIELDS:
            value = values.get(key)
            if not value or (isinstance(value, str) and value.startswith("Open question")):
                missing.append(heading)
            if isinstance(value, (list, tuple)) and not any(str(item).strip() for item in value):
                missing.append(heading)
        return missing

    def _snapshot(self, brief: ReviewBrief, reason: str) -> None:
        self.history.mkdir(parents=True, exist_ok=True)
        snapshot = self.history / f"r{brief.revision:03d}-{reason}.md"
        if not snapshot.exists() and self.path.exists():
            snapshot.write_text(self.path.read_text(encoding="utf-8"), encoding="utf-8")

    def _safe_materials(self, materials: tuple[str | Path, ...]) -> str:
        excerpts: list[str] = []
        for raw_path in materials:
            path = Path(raw_path)
            try:
                resolved = path.resolve()
                resolved.relative_to(self.project_root)
            except ValueError:
                continue
            if resolved.is_symlink() or not resolved.is_file() or resolved.name.startswith("."):
                continue
            try:
                text = resolved.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            excerpts.append(f"- {resolved.relative_to(self.project_root).as_posix()}: {' '.join(text.split())[:1200]}")
        return "\n".join(excerpts)

    def _write(self, brief: ReviewBrief, *, next_action: str, path: Path | None = None) -> None:
        target = path or self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "---",
            "kind: review-brief",
            "schema: 2",
            f"topic: {brief.topic}",
            f"confirmed: {'true' if brief.confirmed else 'false'}",
            f"revision: {brief.revision}",
            f"updated_at: {_now()}",
            "---",
            "",
            "# Review Brief",
            "",
            f"Topic: {brief.topic}",
            "",
        ]
        for key, heading in FIELDS:
            lines.extend((f"## {heading}", ""))
            value = brief.values.get(key, "")
            if key == "core_claims":
                lines.extend(f"- {item}" for item in (value if isinstance(value, (list, tuple)) else (str(value),)))
            else:
                lines.append(_yaml_scalar(value))
            lines.append("")
        lines.extend(("## Known project material", "", str(brief.values.get("known_material", "") or "None supplied explicitly."), ""))
        lines.extend(("## Confirmation and next action", "", f"- Confirmed: {'YES' if brief.confirmed else 'NO'}", f"- Next action: {next_action}", ""))
        target.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Chemical Review v2 Intent stage")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--project", type=Path, required=True)
    init.add_argument("--topic", required=True)
    init.add_argument("--material", type=Path, action="append", default=[])
    confirm = sub.add_parser("confirm")
    confirm.add_argument("--project", type=Path, required=True)
    confirm.add_argument("--decisions-json", type=Path, required=True)
    change = sub.add_parser("propose-change")
    change.add_argument("--project", type=Path, required=True)
    change.add_argument("--changes-json", type=Path, required=True)
    accept = sub.add_parser("confirm-change")
    accept.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    stage = IntentStage(args.project)
    if args.command == "init":
        result = stage.initialize(args.topic, materials=tuple(args.material))
    elif args.command == "confirm":
        result = stage.confirm(json.loads(args.decisions_json.read_text(encoding="utf-8")))
    elif args.command == "propose-change":
        result = stage.propose_change(json.loads(args.changes_json.read_text(encoding="utf-8")))
    else:
        result = stage.confirm_change()
    print(json.dumps({"confirmed": result.confirmed, "revision": result.revision, "next": "Research" if result.confirmed else "human-confirmation"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
