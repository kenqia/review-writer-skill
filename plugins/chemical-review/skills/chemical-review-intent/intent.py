"""Public Intent-stage document contract for Chemical Review v2.

The Intent skill owns only ``review-brief.md`` and its human-readable revision
snapshots.  It deliberately does not import the v1 orchestrator or create a
Python payload for a later stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


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


class ExpertReviewResult:
    """Outcome of the optional, advisory brief review."""

    def __init__(self, *, decision: str, success: bool, findings: Sequence[Mapping[str, Any]] = (), reason: str = ""):
        self.decision = decision
        self.success = success
        self.findings = tuple(dict(item) for item in findings)
        self.reason = reason


EXPERT_MODULES = {
    "research_question", "core_claims", "scope", "scope_time", "exclusions", "audience_contribution", "evidence", "evidence_standards", "boundary_scenarios", "terminology", "primary_study_eligibility", "evidence_matrix", "journal_fit",
}
EXPERT_FINDING_FIELDS = ("id", "module", "severity", "affected_field", "rationale", "suggested_change", "confidence", "unresolved_questions")


@dataclass(frozen=True)
class ReviewBrief:
    topic: str
    confirmed: bool
    values: Mapping[str, str | tuple[str, ...]]
    revision: int = 1


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def _brief_digest(brief: ReviewBrief) -> str:
    payload = {"topic": brief.topic, "revision": brief.revision, "values": dict(brief.values)}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


class IntentStage:
    """Create, confirm, and safely revise a Markdown review brief."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.path = self.project_root / "review-brief.md"
        self.proposed_path = self.project_root / "review-brief.proposed.md"
        self.history = self.project_root / "intent-history"
        self.expert_report_path = self.project_root / "expert-review-report.json"
        self.expert_report_markdown = self.project_root / "expert-review-report.md"
        self.expert_decision_path = self.project_root / "expert-review-decision.md"
        self.expert_prompt_path = self.project_root / "expert-review-prompt.md"

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

    def optional_expert_review(self, choice: str, *, reviewer: Any | None = None, materials: tuple[str | Path, ...] = (), timeout_seconds: float = 60.0, budget: int = 1) -> ExpertReviewResult:
        """Run an isolated advisory check without mutating Intent authority."""
        current = self.read_confirmed()
        normalized = str(choice).strip().lower()
        self._write_expert_prompt(current)
        if normalized in {"no", "skip", "defer"}:
            for path in (self.expert_report_path, self.expert_report_markdown):
                if path.exists():
                    path.unlink()
            decision = "SKIPPED" if normalized in {"no", "skip"} else "DEFERRED"
            self._write_expert_decision(decision, "User chose not to run the optional advisory review.")
            return ExpertReviewResult(decision=decision, success=False, reason="user choice")
        if normalized not in {"yes", "run", "true"}:
            raise ValueError("expert review choice must be yes, no, skip or defer")
        payload = {
            "role": "chemistry-literature journal reviewer (advisory only)",
            "brief": {"topic": current.topic, "revision": current.revision, "values": {key: value for key, value in current.values.items() if key != "known_material"}},
            "material_scope": self._safe_review_materials(materials),
            "required_modules": ["research_question", "core_claims", "scope_time", "exclusions", "audience_contribution", "evidence_standards", "boundary_scenarios", "terminology", "primary_study_eligibility", "evidence_matrix", "journal_fit"],
            "constraints": [
                "Use only this brief and explicitly allowlisted material.",
                "Do not mutate files or produce source facts; report UNKNOWN, NOT_COMPARABLE and Chemical GAP when needed.",
                "This is not formal peer review, journal acceptance prediction or scientific validity certification.",
            ],
        }
        if reviewer is None:
            reason = "UNAVAILABLE: no reviewer was supplied"
            self._write_expert_failure(reason, payload)
            return ExpertReviewResult(decision="FAILED", success=False, reason=reason)
        if budget < 1:
            reason = "BUDGET_EXHAUSTED: reviewer budget must be positive"
            self._write_expert_failure(reason, payload)
            return ExpertReviewResult(decision="FAILED", success=False, reason=reason)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chemical-review-expert")
        future = executor.submit(reviewer.review, payload) if hasattr(reviewer, "review") else executor.submit(reviewer, payload)
        try:
            # Do not use the executor as a context manager here: its __exit__
            # waits for a timed-out callback and would defeat the timeout gate.
            raw = future.result(timeout=max(0.1, float(timeout_seconds)))
        except FutureTimeout:
            reason = "TIMEOUT: advisory reviewer exceeded the configured timeout"
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            self._write_expert_failure(reason, payload)
            return ExpertReviewResult(decision="FAILED", success=False, reason=reason)
        except Exception as exc:  # injected reviewer failures must fail closed without brief mutation
            executor.shutdown(wait=False, cancel_futures=True)
            reason = f"UNAVAILABLE: {type(exc).__name__}"
            self._write_expert_failure(reason, payload)
            return ExpertReviewResult(decision="FAILED", success=False, reason=reason)
        else:
            executor.shutdown(wait=True)
        valid, findings, reason = self._normalize_expert_report(raw)
        if not valid:
            self._write_expert_failure("MALFORMED: " + reason, payload)
            return ExpertReviewResult(decision="FAILED", success=False, reason=reason)
        required_modules = tuple(payload["required_modules"])
        findings = self._enrich_expert_findings(current, findings)
        report = {
            "kind": "chemical-review-intent-expert-advisory",
            "advisory": True,
            "reviewer_role": "chemistry-literature journal reviewer",
            "brief_revision": current.revision,
            "brief_digest": _brief_digest(current),
            "material_scope": payload["material_scope"],
            "findings": findings,
            "module_coverage": {module: ("FINDINGS" if any(finding.get("module") == module for finding in findings) else "NO_FINDING_REPORTED") for module in required_modules},
            "boundary": "Advisory only; canonical review-brief.md is unchanged until selected proposal and confirm_change.",
        }
        self.expert_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = ["# Optional Expert Review (Advisory)", "", "This report is advisory only; it is not formal peer review, a journal-acceptance prediction, or scientific validity certification.", "", f"Brief revision: {current.revision}", "", "## Module coverage", ""] + [f"- {module}: {report['module_coverage'][module]}" for module in required_modules] + ["", "## Findings", ""]
        for finding in findings:
            lines.extend([f"### {finding['id']} · {finding['module']} · {finding['severity']}", "", f"- Affected field: {finding['affected_field']}", f"- Before: {finding.get('before') or 'Current brief value'}", f"- After: {finding.get('after') or finding['suggested_change']}", f"- Rationale: {finding['rationale']}", f"- Suggested change: {finding['suggested_change']}", f"- Confidence: {finding['confidence']}", f"- Unresolved questions: {', '.join(finding['unresolved_questions']) or 'None recorded'}", ""])
        self.expert_report_markdown.write_text("\n".join(lines), encoding="utf-8")
        self._write_expert_decision("PENDING", "Review findings were returned; choose accept-selected, reject-all or defer.")
        return ExpertReviewResult(decision="PENDING", success=True, findings=findings)

    # Friendly aliases for callers that describe the interaction differently.
    run_optional_expert_review = optional_expert_review
    review_completed_brief = optional_expert_review

    def grouped_expert_findings(self) -> dict[str, tuple[Mapping[str, Any], ...]]:
        if not self.expert_report_path.is_file():
            return {}
        try:
            report = json.loads(self.expert_report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        display_modules = {
            "scope_time": "scope", "exclusions": "scope", "audience_contribution": "journal_fit",
            "evidence_standards": "evidence", "boundary_scenarios": "evidence", "primary_study_eligibility": "evidence",
            "evidence_matrix": "evidence_matrix",
        }
        for finding in report.get("findings", []) if isinstance(report, Mapping) else ():
            if isinstance(finding, Mapping):
                module = display_modules.get(str(finding.get("module", "scope")), str(finding.get("module", "scope")))
                grouped.setdefault(module, []).append(finding)
        return {module: tuple(items) for module, items in grouped.items()}

    def apply_expert_review_decision(self, decision: str, *, selected: Sequence[str | Mapping[str, Any]] = ()) -> str:
        normalized = str(decision).strip().lower()
        if normalized in {"reject-all", "reject_all", "defer"}:
            label = "REJECT_ALL" if normalized != "defer" else "DEFERRED"
            self._write_expert_decision(label, "Canonical brief preserved; no suggestion was applied.")
            return label
        if normalized not in {"accept-selected", "accept_selected"}:
            raise ValueError("expert review decision must be accept-selected, reject-all or defer")
        if not self.expert_report_path.is_file():
            raise ValueError("no successful expert review report exists")
        report = json.loads(self.expert_report_path.read_text(encoding="utf-8"))
        current = self.read_any(ignore_pending=True)
        if report.get("status") == "FAILED" or report.get("advisory") is not True:
            raise ConfirmationRequired("expert report is not a successful advisory report")
        if report.get("brief_revision") != current.revision or report.get("brief_digest") != _brief_digest(current):
            raise ConfirmationRequired("expert report is stale for the current confirmed brief")
        findings = report.get("findings", []) if isinstance(report, Mapping) else []
        requested = {item if isinstance(item, str) else str(item.get("id", "")) for item in selected}
        chosen = [finding for finding in findings if isinstance(finding, Mapping) and str(finding.get("id", "")) in requested]
        if not chosen:
            self._write_expert_decision("REJECT_ALL", "No valid finding was selected; canonical brief preserved.")
            return "REJECT_ALL"
        changes: dict[str, object] = {}
        for finding in chosen:
            field = str(finding.get("affected_field", "")).strip()
            if field not in {name for name, _heading in FIELDS}:
                continue
            suggestion = str(finding.get("suggested_change", "")).strip()
            if field == "core_claims":
                current = self.read_any(ignore_pending=True).values.get(field, ())
                changes[field] = tuple(current if isinstance(current, (tuple, list)) else (str(current),)) + ((suggestion,) if suggestion else ())
            elif suggestion:
                changes[field] = suggestion
        if not changes:
            self._write_expert_decision("REJECT_ALL", "Selected findings did not map to an editable Intent field.")
            return "REJECT_ALL"
        self.propose_change(changes)
        self._write_expert_decision("PROPOSED", "Selected advisory suggestions were written to review-brief.proposed.md; confirm_change remains mandatory.")
        return "PROPOSED"

    def _safe_review_materials(self, materials: tuple[str | Path, ...]) -> str:
        allowed_names = {"project-context.md", "domain-profile.md", "research-handoff.md", "research-evidence.md"}
        excerpts: list[str] = []
        for raw_path in materials:
            path = Path(raw_path)
            try:
                if path.is_symlink():
                    continue
                resolved = path.resolve()
                resolved.relative_to(self.project_root)
            except ValueError:
                continue
            if not resolved.is_file() or resolved.name.startswith("."):
                continue
            if resolved.name not in allowed_names and not resolved.name.startswith("evidence-"):
                continue
            try:
                text = resolved.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            safe_text = re.sub(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
            excerpts.append(f"- {resolved.relative_to(self.project_root).as_posix()}: {' '.join(safe_text.split())[:1200]}")
        return "\n".join(excerpts) or "None supplied explicitly."

    @staticmethod
    def _normalize_expert_report(raw: Any) -> tuple[bool, list[dict[str, Any]], str]:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("findings"), (list, tuple)):
            return False, [], "report must contain a findings list"
        findings: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        module_aliases = {
            "evidence_matrix_implications": "evidence_matrix",
            "journal_fit_contribution": "journal_fit",
        }
        for index, raw_finding in enumerate(raw["findings"]):
            if not isinstance(raw_finding, Mapping):
                return False, [], f"finding {index + 1} is not an object"
            finding = dict(raw_finding)
            missing = [field for field in EXPERT_FINDING_FIELDS if field not in finding]
            if missing:
                return False, [], f"finding {index + 1} missing: {', '.join(missing)}"
            finding_id = str(finding["id"]).strip()
            if not finding_id:
                return False, [], f"finding {index + 1} has an empty id"
            if finding_id in seen_ids:
                return False, [], f"finding {index + 1} duplicates id {finding_id}"
            seen_ids.add(finding_id)
            module = str(finding["module"]).strip().lower().replace(" ", "_").replace("-", "_")
            module = module_aliases.get(module, module)
            if module not in EXPERT_MODULES:
                return False, [], f"finding {index + 1} has unknown module {module}"
            finding["module"] = module
            finding["unresolved_questions"] = [str(item) for item in (finding["unresolved_questions"] if isinstance(finding["unresolved_questions"], (list, tuple)) else [finding["unresolved_questions"]]) if str(item).strip()]
            finding.setdefault("before", "")
            finding.setdefault("after", str(finding.get("suggested_change", "")))
            findings.append({**{field: finding[field] for field in EXPERT_FINDING_FIELDS}, "before": str(finding.get("before", "")), "after": str(finding.get("after", ""))})
        return True, findings, ""

    @staticmethod
    def _enrich_expert_findings(brief: ReviewBrief, findings: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for finding in findings:
            item = dict(finding)
            field = str(item.get("affected_field", ""))
            # The reviewer cannot author the baseline. Recompute `before`
            # from the current canonical brief so a stale/misleading callback
            # payload cannot be presented as an applied delta.
            before = brief.values.get(field, "UNKNOWN")
            item["before"] = _yaml_scalar(before) or "UNKNOWN"
            item["after"] = str(item.get("after") or item.get("suggested_change") or "UNKNOWN")
            enriched.append(item)
        return enriched

    def _write_expert_decision(self, decision: str, detail: str) -> None:
        self.expert_decision_path.write_text(f"# Expert Review Decision\n\nDecision: {decision}\n\n{detail}\n", encoding="utf-8")

    def _write_expert_prompt(self, brief: ReviewBrief) -> None:
        lines = ["# Completed Review Brief — Optional Advisory Review", "", "Inspect this brief before choosing yes, no or skip. The following check is optional and advisory.", "", f"Topic: {brief.topic}", ""]
        for key, heading in FIELDS:
            value = brief.values.get(key, "")
            lines.extend([f"## {heading}", "", _yaml_scalar(value), ""])
        self.expert_prompt_path.write_text("\n".join(lines), encoding="utf-8")

    def _write_expert_failure(self, reason: str, payload: Mapping[str, Any]) -> None:
        report = {"kind": "chemical-review-intent-expert-advisory", "advisory": True, "status": "FAILED", "reason": reason, "material_scope": payload.get("material_scope", "None supplied explicitly."), "findings": []}
        self.expert_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.expert_report_markdown.write_text("# Optional Expert Review (Advisory)\n\nStatus: FAILED\n\n" + reason + "\n", encoding="utf-8")
        self._write_expert_decision("FAILED", reason)

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
        allowed_names = {"project-context.md", "domain-profile.md", "research-handoff.md", "research-evidence.md"}
        excerpts: list[str] = []
        for raw_path in materials:
            path = Path(raw_path)
            try:
                if path.is_symlink():
                    continue
                resolved = path.resolve()
                resolved.relative_to(self.project_root)
            except ValueError:
                continue
            if not resolved.is_file() or resolved.name.startswith("."):
                continue
            if resolved.name not in allowed_names and not resolved.name.startswith("evidence-"):
                continue
            try:
                text = resolved.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            safe_text = re.sub(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
            excerpts.append(f"- {resolved.relative_to(self.project_root).as_posix()}: {' '.join(safe_text.split())[:1200]}")
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
    expert = sub.add_parser("expert-review")
    expert.add_argument("--project", type=Path, required=True)
    expert.add_argument("--choice", choices=("yes", "no", "skip", "defer"), required=True)
    expert.add_argument("--fixture-json", type=Path)
    expert.add_argument("--material", type=Path, action="append", default=[])
    expert.add_argument("--timeout-seconds", type=float, default=60.0)
    expert.add_argument("--budget", type=int, default=1)
    expert_decision = sub.add_parser("expert-decision")
    expert_decision.add_argument("--project", type=Path, required=True)
    expert_decision.add_argument("--decision", choices=("accept-selected", "reject-all", "defer"), required=True)
    expert_decision.add_argument("--selected", action="append", default=[])
    args = parser.parse_args()
    stage = IntentStage(args.project)
    if args.command == "init":
        result = stage.initialize(args.topic, materials=tuple(args.material))
    elif args.command == "confirm":
        result = stage.confirm(json.loads(args.decisions_json.read_text(encoding="utf-8")))
    elif args.command == "propose-change":
        result = stage.propose_change(json.loads(args.changes_json.read_text(encoding="utf-8")))
    elif args.command == "confirm-change":
        result = stage.confirm_change()
    elif args.command == "expert-review":
        reviewer = None
        if args.fixture_json:
            fixture = json.loads(args.fixture_json.read_text(encoding="utf-8"))
            def fixture_reviewer(_payload: Mapping[str, Any]) -> Any:
                return fixture
            reviewer = fixture_reviewer
        result = stage.optional_expert_review(
            args.choice,
            reviewer=reviewer,
            materials=tuple(args.material),
            timeout_seconds=args.timeout_seconds,
            budget=args.budget,
        )
        print(json.dumps({"decision": result.decision, "success": result.success, "findings": len(result.findings), "reason": result.reason}, ensure_ascii=False))
        return 0 if result.success or result.decision in {"SKIPPED", "DEFERRED"} else 2
    else:
        decision = stage.apply_expert_review_decision(args.decision, selected=args.selected)
        print(json.dumps({"decision": decision}, ensure_ascii=False))
        return 0
    print(json.dumps({"confirmed": result.confirmed, "revision": result.revision, "next": "Research" if result.confirmed else "human-confirmation"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
