"""Evidence-bounded Synthesis producer for Chemical Review v2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import re


class EvidenceBoundaryError(ValueError):
    """A candidate draft makes a source claim without a registered locator."""


@dataclass(frozen=True)
class DraftResult:
    status: str
    path: Path
    next_action: str
    revision: int


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class SynthesisStage:
    """Publish one current draft while keeping Research and QA ownership separate."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.draft_path = self.project_root / "draft.md"
        self.history = self.project_root / "synthesis-history"

    def scaffold(self) -> str:
        handoff = self._research_handoff()
        partial = "RESEARCH_GAP" in handoff or "WAITING_FOR_USER" in handoff
        status = "unreviewed; evidence-bounded; partial-scope" if partial else "unreviewed; evidence-bounded"
        return "\n".join(
            [
                "# Candidate Chemical Review", "", f"Status: {status}", "",
                "## Scope and contribution", "", "State the confirmed review question and contribution from review-brief.md.", "",
                "## Comparative synthesis", "", "Compare studies under matched conditions, units, endpoints, and mechanisms.", "",
                "## Explanation and rebuttal", "", "Separate SOURCE_FACT, MODEL_SYNTHESIS, and MODEL_HYPOTHESIS; cite every source fact with a locator.", "",
                "## Trends and testable hypotheses", "", "Describe trends only within the evidence boundary and label hypotheses explicitly.", "",
                "## Evidence boundary", "", "UNKNOWN: [state the missing variable].", "NOT_COMPARABLE: [state why a comparison cannot be made].", "Chemical GAP: [state the highest-impact missing source or condition].", "",
                "## Next action", "", "Return to Research for missing core full text, or proceed to QA only for the bounded scope.", "",
            ]
        )

    def publish(self, candidate: str | Path) -> DraftResult:
        self._require_intent()
        handoff = self._research_handoff()
        candidate_path = Path(candidate)
        content = candidate_path.read_text(encoding="utf-8") if candidate_path.is_file() else str(candidate)
        if not content.strip():
            raise ValueError("candidate draft cannot be blank")
        evidence = (self.project_root / "research" / "evidence-notes.md").read_text(encoding="utf-8") if (self.project_root / "research" / "evidence-notes.md").is_file() else ""
        self._validate_source_facts(content, evidence)
        partial = "RESEARCH_GAP" in handoff or "WAITING_FOR_USER" in handoff
        if partial and not re.search(r"unreviewed|partial-scope|evidence-bounded", content, re.I):
            raise EvidenceBoundaryError("partial Research requires an explicit unreviewed, evidence-bounded, partial-scope marker")
        if "SOURCE_FACT" in content and not re.search(r"SOURCE_FACT\s*\[", content):
            raise EvidenceBoundaryError("SOURCE_FACT must carry [source identity @ locator]")
        revision = self._next_revision()
        if self.draft_path.exists():
            self.history.mkdir(parents=True, exist_ok=True)
            snapshot = self.history / f"r{revision:03d}-before-publish.md"
            snapshot.write_text(self.draft_path.read_text(encoding="utf-8"), encoding="utf-8")
        status = "UNREVIEWED_PARTIAL" if partial else "UNREVIEWED"
        header = "\n".join(["---", "kind: synthesis-draft", "schema: 2", f"status: {status}", f"revision: {revision}", f"updated_at: {_now()}", "owner: Synthesis", "---", ""])
        self.draft_path.write_text(header + content.rstrip() + "\n", encoding="utf-8")
        next_action = "Return to Research before broadening scope." if partial else "Proceed to QA with four independent clean-context reviews."
        (self.project_root / "synthesis-handoff.md").write_text(
            "\n".join(["# Synthesis Handoff", "", f"Result: {status}", f"Draft: {self.draft_path.name}", f"Next action: {next_action}", "", "Synthesis owns draft.md. Research artifacts are read-only inputs; QA may report issues but must not mutate the draft.", ""]),
            encoding="utf-8",
        )
        return DraftResult(status, self.draft_path, next_action, revision)

    def _require_intent(self) -> None:
        path = self.project_root / "review-brief.md"
        if not path.is_file() or not re.search(r"^confirmed:\s*true\s*$", path.read_text(encoding="utf-8"), re.M):
            raise RuntimeError("HUMAN_ACTION_REQUIRED: Synthesis requires confirmed review-brief.md")
        if (self.project_root / "review-brief.proposed.md").exists():
            raise RuntimeError("HUMAN_ACTION_REQUIRED: proposed intent change is not confirmed")

    def _research_handoff(self) -> str:
        path = self.project_root / "research" / "research-handoff.md"
        if not path.is_file():
            raise FileNotFoundError("Research handoff is missing")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _validate_source_facts(content: str, evidence: str) -> None:
        for match in re.finditer(r"SOURCE_FACT\s*\[([^\]@]+)\s*@\s*([^\]]+)\]", content):
            identity, locator = match.group(1).strip(), match.group(2).strip()
            verified = re.search(rf"(?:VERIFIED_)?SOURCE_FACT\s*\[{re.escape(identity)}\s*@\s*{re.escape(locator)}\]", evidence)
            if not verified:
                raise EvidenceBoundaryError(f"verified SOURCE_FACT locator is not present in Research evidence notes: {identity} @ {locator}")

    def _next_revision(self) -> int:
        if not self.draft_path.exists():
            return 1
        text = self.draft_path.read_text(encoding="utf-8")
        match = re.search(r"^revision:\s*(\d+)", text, re.M)
        return int(match.group(1)) + 1 if match else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Chemical Review v2 Synthesis stage")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--scaffold", action="store_true")
    args = parser.parse_args()
    stage = SynthesisStage(args.project)
    if args.scaffold:
        print(stage.scaffold())
        return 0
    if args.candidate is None:
        raise SystemExit("--candidate is required unless --scaffold is used")
    result = stage.publish(args.candidate)
    print(json.dumps({"status": result.status, "draft": str(result.path), "next_action": result.next_action}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
