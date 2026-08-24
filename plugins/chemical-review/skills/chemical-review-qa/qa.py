"""Isolated multi-angle QA handoff for Chemical Review v2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping


ROLES = (
    ("evidence-locator", "Evidence and locator", "Check every source fact, identity, locator, and parser degradation."),
    ("chemistry-comparability", "Chemistry comparability and mechanism", "Check conditions, units, endpoints, mechanisms, and NOT_COMPARABLE boundaries."),
    ("synthesis-novelty", "Synthesis novelty and rebuttal", "Check comparison, explanation, rebuttal, trends, hypotheses, and contribution beyond summary."),
    ("overclaim-counterexample", "Overclaim and counterexample", "Challenge scope drift, unsupported certainty, counterexamples, UNKNOWN, and Chemical GAP."),
)


@dataclass(frozen=True)
class QAResult:
    round_id: str
    report_path: Path
    conflicts: tuple[str, ...]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class QAStage:
    """Prepare equal clean contexts and aggregate reports without voting."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.root = self.project_root / "qa"

    def prepare(self) -> tuple[Path, ...]:
        for required in (self.project_root / "review-brief.md", self.project_root / "draft.md", self.project_root / "research" / "research-handoff.md"):
            if not required.is_file():
                raise FileNotFoundError(f"QA input is missing: {required}")
        round_root = self._next_round()
        source_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (self.project_root / "review-brief.md", self.project_root / "research" / "research-handoff.md", self.project_root / "research" / "evidence-notes.md", self.project_root / "draft.md")
            if path.is_file()
        )
        contexts: list[Path] = []
        for slug, label, instruction in ROLES:
            role = round_root / "roles" / slug
            role.mkdir(parents=True, exist_ok=True)
            (role / "context.md").write_text(source_text, encoding="utf-8")
            (role / "role-instructions.md").write_text("\n".join([f"# {label}", "", instruction, "", "Write an independent report. Do not read other role folders or mutate draft.md.", "Required fields: cited locator, severity, rationale, earliest return stage.", ""]), encoding="utf-8")
            (role / "input-manifest.md").write_text(f"# Clean Context Manifest\n\n- input_digest: {hashlib.sha256(source_text.encode()).hexdigest()}\n- prior_reports_visible: NO\n- draft_mutation_allowed: NO\n", encoding="utf-8")
            contexts.append(role)
        (round_root / "README.md").write_text("# QA Round\n\nFour roles must run independently from the same input digest. The arbiter reads reports only after all roles finish; disagreements are preserved.\n", encoding="utf-8")
        return tuple(contexts)

    def write_fixture_reports(self, reports: Mapping[str, str]) -> tuple[Path, ...]:
        rounds = sorted(self.root.glob("round-*"))
        if not rounds:
            self.prepare()
            rounds = sorted(self.root.glob("round-*"))
        round_root = rounds[-1]
        paths: list[Path] = []
        for slug, _label, _instruction in ROLES:
            role = round_root / "roles" / slug
            path = role / "report.md"
            text = reports.get(slug, "severity: LOW\nrationale: no finding\nearliest return stage: Synthesis\n")
            path.write_text(f"# Independent QA Report\n\nRole: {slug}\n\n{text.rstrip()}\n", encoding="utf-8")
            paths.append(path)
        return tuple(paths)

    def finalize(self) -> QAResult:
        rounds = sorted(self.root.glob("round-*"))
        if not rounds:
            raise FileNotFoundError("no QA round exists; run prepare first")
        round_root = rounds[-1]
        reports: list[tuple[str, str]] = []
        for slug, _label, _instruction in ROLES:
            path = round_root / "roles" / slug / "report.md"
            if not path.is_file():
                raise RuntimeError(f"HUMAN_ACTION_REQUIRED: independent QA report missing for {slug}")
            reports.append((slug, path.read_text(encoding="utf-8")))
        conflicts = self._conflicts(reports)
        report_lines = ["# QA Review Report", "", f"Round: {round_root.name}", f"Generated: {_now()}", "", "The following reports were produced from isolated clean contexts. The arbiter preserves disagreements; this is advice, not scientific acceptance.", ""]
        for slug, text in reports:
            report_lines.extend([f"## {slug}", "", text.rstrip(), ""])
        report_lines.extend(["## Preserved conflicts", ""])
        report_lines.extend(f"- {conflict}" for conflict in conflicts)
        if not conflicts:
            report_lines.append("- None detected by the deterministic aggregator.")
        report_lines.append("")
        report_path = self.root / "review-report.md"
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        (self.root / "qa-plan.md").write_text("\n".join(["# QA Plan", "", "- Human scientist reviews each independent report and every cited locator.", "- Resolve HIGH evidence/chemistry findings before expanding scope.", "- Preserve UNKNOWN, NOT_COMPARABLE, and Chemical GAP in any revision.", "- QA does not accept scientific validity or mutate draft.md.", ""]), encoding="utf-8")
        routes = self._routes(reports)
        (self.root / "revision-plan.md").write_text("\n".join(["# Revision Plan", "", "Earliest-stage routing (human decides):", ""] + [f"- {stage}: {reason}" for stage, reason in routes] + ["", "Previous QA reports remain under the round directory; a rerun appends a new round.", ""]), encoding="utf-8")
        return QAResult(round_root.name, report_path, tuple(conflicts))

    def route_feedback(self, feedback: str) -> str:
        if not feedback.strip():
            raise ValueError("feedback cannot be blank")
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "feedback.md").write_text("# Human Feedback\n\n" + feedback.strip() + "\n", encoding="utf-8")
        lowered = feedback.lower()
        stage = "Intent" if any(word in lowered for word in ("scope", "question", "audience", "exclusion")) else "Research" if any(word in lowered for word in ("source", "paper", "full text", "locator", "evidence")) else "Synthesis"
        (self.root / "revision-plan.md").write_text(f"# Revision Plan\n\n- Earliest return stage: {stage}\n- Reason: preserved natural-language human feedback.\n- Action: human confirms the rerun; existing reports and draft remain unchanged.\n", encoding="utf-8")
        return stage

    def _next_round(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        numbers = [int(match.group(1)) for path in self.root.glob("round-*") if (match := re.match(r"round-(\d+)$", path.name))]
        round_root = self.root / f"round-{(max(numbers) + 1 if numbers else 1):03d}"
        round_root.mkdir(parents=True, exist_ok=True)
        return round_root

    @staticmethod
    def _conflicts(reports: list[tuple[str, str]]) -> list[str]:
        severities: dict[str, list[str]] = {}
        explicit: list[str] = []
        for slug, text in reports:
            for line in text.splitlines():
                if "conflict" in line.lower():
                    explicit.append(f"{slug}: {line.strip()}")
                match = re.search(r"^severity\s*:\s*([^\n]+)", line, re.I)
                if match:
                    severities.setdefault(match.group(1).strip().lower(), []).append(slug)
        if explicit:
            return explicit
        if len(severities) > 1:
            detail = ", ".join(f"{key} ({', '.join(roles)})" for key, roles in severities.items())
            return [f"roles recorded different severities: {detail}"]
        return []

    @staticmethod
    def _routes(reports: list[tuple[str, str]]) -> list[tuple[str, str]]:
        routes: list[tuple[str, str]] = []
        for slug, text in reports:
            match = re.search(r"earliest(?: return)? stage\s*:\s*([^\n]+)", text, re.I)
            stage = match.group(1).strip() if match else ("Research" if slug == "evidence-locator" else "Synthesis")
            routes.append((stage, f"{slug} report; inspect its cited locator and rationale."))
        return routes


def main() -> int:
    parser = argparse.ArgumentParser(description="Chemical Review v2 QA stage")
    parser.add_argument("command", choices=("prepare", "finalize", "feedback"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--text")
    args = parser.parse_args()
    stage = QAStage(args.project)
    if args.command == "prepare":
        print(json.dumps({"contexts": [str(path) for path in stage.prepare()]}, ensure_ascii=False))
    elif args.command == "finalize":
        result = stage.finalize()
        print(json.dumps({"round": result.round_id, "report": str(result.report_path), "conflicts": result.conflicts}, ensure_ascii=False))
    else:
        print(json.dumps({"earliest_return_stage": stage.route_feedback(args.text or "")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
