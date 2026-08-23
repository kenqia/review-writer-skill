"""Small-sample review Prototype and adaptable PRD blueprint behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
from pathlib import Path
from typing import Mapping

from orchestrator import (
    _document,
    _replace_frontmatter,
    _section_value,
    _set_section,
    _split_frontmatter,
)


SIGNAL_HEADINGS = {
    "comparison": "Comparisons",
    "explanation": "Explanations",
    "rebuttal": "Rebuttals",
    "new_research_question": "New research questions",
}


@dataclass(frozen=True)
class PrototypeSignal:
    """One evidence-bound claim that adds value beyond fluent summary."""

    kind: str
    statement: str
    evidence_ids: tuple[str, ...]
    value_gain: str


@dataclass(frozen=True)
class PrototypeSubmission:
    """Agent-produced small-sample analysis; the researcher does not fill this as a form."""

    paper_ids: tuple[str, ...] = ()
    subsection: str = ""
    subsection_evidence_ids: tuple[str, ...] = ()
    representative_reason: str = ""
    draft: str = ""
    value_argument: str = ""
    signals: tuple[PrototypeSignal, ...] = ()
    risks: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlueprintProposal:
    """Agent-produced executable outline derived from saved project assets."""

    section_structure: tuple[str, ...]
    narrative_line: str
    comparison_dimensions: tuple[str, ...]
    evidence_strategy: tuple[str, ...]
    target_journal_requirements: tuple[str, ...]
    known_risks: tuple[str, ...]
    candidate_units: tuple[str, ...]


@dataclass(frozen=True)
class PrototypeResult:
    value_status: str
    handoff: str
    rationale: str
    value_dimensions: tuple[str, ...]
    risks: tuple[str, ...]


class PrototypeRunner:
    """Evaluate whether a small sample supports non-trivial review synthesis."""

    TRACKED_SECTIONS = (
        "Selection",
        "Representative rationale",
        "Prototype draft",
        "Value argument",
        *SIGNAL_HEADINGS.values(),
        "Major risks",
        "Prototype decision",
    )

    def __init__(self, project_root: str | Path, *, today: date | None = None) -> None:
        self.project_root = Path(project_root)
        self.today = today or date.today()

    @property
    def result_path(self) -> Path:
        return self.project_root / "prototype-result.md"

    def run(self, submission: PrototypeSubmission) -> PrototypeResult:
        selected_evidence = self._validate_selection(submission)
        self._validate_signals(submission.signals, selected_evidence)
        dimensions = tuple(
            heading.lower()
            for kind, heading in SIGNAL_HEADINGS.items()
            if any(signal.kind == kind for signal in submission.signals)
        )
        if dimensions and submission.value_argument.strip():
            value_status = "VALUE_PRODUCING"
            handoff = "PRD"
            rationale = (
                "The sample produced non-trivial "
                + ", ".join(dimensions)
                + f". Claimed value: {submission.value_argument.strip()}. "
                "This is a handoff proposal, not proof that the interpretation is correct."
            )
        else:
            value_status = "SUMMARY_ONLY"
            handoff = "RESEARCH"
            rationale = (
                "Fluent summary is not sufficient: the sample contains no explicit comparison, "
                "explanation, rebuttal, or new research question paired with a clear value argument."
            )
        self._persist(submission, value_status, handoff, rationale, dimensions)
        return PrototypeResult(
            value_status=value_status,
            handoff=handoff,
            rationale=rationale,
            value_dimensions=dimensions,
            risks=submission.risks,
        )

    def _validate_selection(self, submission: PrototypeSubmission) -> tuple[str, ...]:
        if not submission.paper_ids and not submission.subsection.strip():
            raise ValueError("Prototype requires selected Research paper IDs or one subsection.")
        if submission.paper_ids and submission.subsection.strip():
            raise ValueError("Prototype selects either Research paper IDs or one subsection, not both.")
        if submission.paper_ids and submission.subsection_evidence_ids:
            raise ValueError("Paper selection cannot also provide subsection evidence IDs.")
        if submission.subsection.strip() and not _nonblank(submission.subsection_evidence_ids):
            raise ValueError("Prototype subsection selection requires Research evidence IDs.")
        if not submission.representative_reason.strip():
            raise ValueError("Prototype must explain why this small sample is representative.")
        evidence_path = self.project_root / "research-evidence.md"
        literature_path = self.project_root / "literature-set.md"
        if not evidence_path.exists() or not literature_path.exists():
            raise FileNotFoundError("Prototype requires saved Research evidence and literature assets.")
        selected = (
            _nonblank(submission.paper_ids)
            if submission.paper_ids
            else _nonblank(submission.subsection_evidence_ids)
        )
        if not selected:
            raise ValueError("Prototype selection requires at least one non-empty Research evidence ID.")
        literature = literature_path.read_text(encoding="utf-8")
        available = _literature_evidence_ids(literature)
        missing = set(selected) - available
        if missing:
            raise ValueError(
                "Prototype selection is absent from Research literature-set.md: "
                + ", ".join(sorted(missing))
            )
        return selected

    def _validate_signals(
        self, signals: tuple[PrototypeSignal, ...], selected_evidence: tuple[str, ...]
    ) -> None:
        selected = set(selected_evidence)
        for signal in signals:
            if signal.kind not in SIGNAL_HEADINGS:
                raise ValueError("Unknown Prototype signal kind: " + signal.kind)
            if not signal.statement.strip() or not signal.value_gain.strip():
                raise ValueError("Prototype signals require a statement and value beyond summary.")
            evidence_ids = _nonblank(signal.evidence_ids)
            if not evidence_ids:
                raise ValueError("Prototype signals must cite selected Research evidence.")
            outside_selection = set(evidence_ids) - selected
            if outside_selection:
                raise ValueError(
                    "Prototype signals may cite only selected Research evidence: "
                    + ", ".join(sorted(outside_selection))
                )
            if signal.kind == "comparison" and len(set(evidence_ids)) < 2:
                raise ValueError("A comparison signal requires at least two selected evidence records.")

    def _persist(
        self,
        submission: PrototypeSubmission,
        value_status: str,
        handoff: str,
        rationale: str,
        dimensions: tuple[str, ...],
    ) -> None:
        revision = 0
        history = "No earlier Prototype run."
        human_notes = ""
        preserved_edits = ""
        if self.result_path.exists():
            previous = self.result_path.read_text(encoding="utf-8")
            metadata, _ = _split_frontmatter(previous)
            revision = int(metadata.get("prototype_revision", "0")) + 1
            previous_history = _section_value(previous, "Revision history")
            history_entry = (
                f"### Revision {revision - 1}\n\n"
                f"Previous value status: {metadata.get('value_status', 'UNKNOWN')}\n\n"
                f"Previous handoff: {metadata.get('prototype_handoff', 'NONE')}\n\n"
                f"Previous decision:\n{_section_value(previous, 'Prototype decision')}"
            )
            history = (
                history_entry
                if previous_history == "No earlier Prototype run."
                else previous_history.rstrip() + "\n\n" + history_entry
            )
            human_notes = _section_value(previous, "Human notes")
            preserved_edits = _section_value(previous, "Preserved human edits and conflicts")
            for heading in self.TRACKED_SECTIONS:
                expected_hash = metadata.get(_hash_key(heading))
                previous_value = _section_value(previous, heading)
                if expected_hash and _content_hash(previous_value) != expected_hash:
                    conflict = (
                        f"### Preserved direct edit from {heading} before revision {revision}\n\n"
                        "The section differed from the last generated version and was kept as rerun input:\n\n"
                        f"```md\n{previous_value.rstrip()}\n```"
                    )
                    if conflict not in preserved_edits:
                        preserved_edits = (preserved_edits.rstrip() + "\n\n" + conflict).strip()
        selection_mode = "PAPERS" if submission.paper_ids else "SUBSECTION"
        metadata = {
            "kind": "small-sample-review-prototype",
            "schema": "1",
            "prototype_revision": str(revision),
            "selection_mode": selection_mode,
            "value_status": value_status,
            "prototype_handoff": handoff,
            "status": "READY_FOR_NEXT_PHASE",
            "updated": self.today.isoformat(),
        }
        body = (
            "# Small-sample Review Prototype\n\n"
            "## Selection\n"
            f"{_selection_text(submission)}\n\n"
            "## Representative rationale\n"
            f"{submission.representative_reason}\n\n"
            "## Prototype draft\n"
            f"{submission.draft or 'No prose draft supplied; analytical outputs are evaluated directly.'}\n\n"
            "## Value argument\n"
            f"{submission.value_argument or 'No non-trivial value argument demonstrated.'}\n\n"
            "## Comparisons\n"
            f"{_render_signals(submission.signals, 'comparison')}\n\n"
            "## Explanations\n"
            f"{_render_signals(submission.signals, 'explanation')}\n\n"
            "## Rebuttals\n"
            f"{_render_signals(submission.signals, 'rebuttal')}\n\n"
            "## New research questions\n"
            f"{_render_signals(submission.signals, 'new_research_question')}\n\n"
            "## Major risks\n"
            f"{_items(submission.risks)}\n\n"
            "## Prototype decision\n"
            f"Value status: {value_status}\n\n"
            f"Observed dimensions: {', '.join(dimensions) if dimensions else 'none'}\n\n"
            f"Rationale: {rationale}\n\n"
            f"Proposed next phase: {handoff}\n\n"
            "## Revision history\n"
            f"{history}\n\n"
            "## Preserved human edits and conflicts\n"
            f"{preserved_edits}\n\n"
            "## Human notes\n"
            f"{human_notes}\n"
        )
        document = _document(metadata, body)
        document = _record_generated_hashes(document, self.TRACKED_SECTIONS)
        self.result_path.write_text(document.rstrip() + "\n", encoding="utf-8")


class BlueprintBuilder:
    """Create and revise a lightweight review blueprint from saved assets."""

    CHANGEABLE_SECTIONS = {
        "section_structure": "Section structure",
        "narrative_line": "Narrative line",
        "comparison_dimensions": "Comparison dimensions",
        "evidence_strategy": "Evidence strategy",
        "target_journal_requirements": "Target-journal requirements",
        "known_risks": "Known risks",
        "candidate_units": "Candidate research/writing units",
    }

    def __init__(self, project_root: str | Path, *, today: date | None = None) -> None:
        self.project_root = Path(project_root)
        self.today = today or date.today()

    @property
    def blueprint_path(self) -> Path:
        return self.project_root / "review-blueprint.md"

    def build(self, proposal: BlueprintProposal) -> int:
        if self.blueprint_path.exists():
            raise FileExistsError("review-blueprint.md exists; revise it instead of overwriting it.")
        self._validate_proposal(proposal)
        intent_path = self.project_root / "review-intent.md"
        evidence_path = self.project_root / "research-evidence.md"
        if not intent_path.exists() or not evidence_path.exists():
            raise FileNotFoundError("PRD requires saved Review Intent and Research evidence assets.")
        intent = intent_path.read_text(encoding="utf-8")
        prototype_path = self.project_root / "prototype-result.md"
        if prototype_path.exists():
            prototype = prototype_path.read_text(encoding="utf-8")
            prototype_basis = _section_value(prototype, "Prototype decision")
        else:
            prototype_basis = "Research proposed a direct PRD handoff; no Prototype asset exists."
        metadata = {
            "kind": "review-blueprint",
            "schema": "1",
            "blueprint_revision": "0",
            "blueprint_status": "ADAPTABLE",
            "frozen": "false",
            "updated": self.today.isoformat(),
        }
        body = (
            "# Review Blueprint\n\n"
            "This blueprint is adaptive: evidence can revise sections, comparison dimensions, and units. "
            "It does not assign every sentence or freeze a paper list.\n\n"
            "## Research question\n"
            f"{_section_value(intent, 'Research question')}\n\n"
            "## Core-claim candidates\n"
            f"{_section_value(intent, 'Core-claim candidates')}\n\n"
            "## Section structure\n"
            f"{_items(proposal.section_structure)}\n\n"
            "## Narrative line\n"
            f"{proposal.narrative_line}\n\n"
            "## Comparison dimensions\n"
            f"{_items(proposal.comparison_dimensions)}\n\n"
            "## Evidence strategy\n"
            f"{_items(proposal.evidence_strategy)}\n\n"
            "## Expected contribution\n"
            f"{_section_value(intent, 'Expected contribution')}\n\n"
            "## Target-journal requirements\n"
            f"{_items(proposal.target_journal_requirements)}\n\n"
            "## Prototype basis\n"
            f"{prototype_basis}\n\n"
            "## Known risks\n"
            f"{_items(proposal.known_risks)}\n\n"
            "## Candidate research/writing units\n"
            f"{_items(proposal.candidate_units)}\n\n"
            "## Revision history\n"
            "No revisions yet.\n\n"
            "## Human notes\n"
        )
        document = _document(metadata, body)
        document = _record_generated_hashes(document, self.CHANGEABLE_SECTIONS.values())
        self.blueprint_path.write_text(document.rstrip() + "\n", encoding="utf-8")
        return 0

    def revise(self, changes: Mapping[str, str | tuple[str, ...]], *, evidence_note: str) -> int:
        if not self.blueprint_path.exists():
            raise FileNotFoundError("Build review-blueprint.md before revising it.")
        if not evidence_note.strip():
            raise ValueError("Blueprint revision requires an evidence or reasoning note.")
        if not changes:
            raise ValueError("Blueprint revision requires at least one affected section.")
        unknown = set(changes) - set(self.CHANGEABLE_SECTIONS)
        if unknown:
            raise ValueError("Unknown blueprint sections: " + ", ".join(sorted(unknown)))
        blueprint = self.blueprint_path.read_text(encoding="utf-8")
        metadata, _ = _split_frontmatter(blueprint)
        revision = int(metadata.get("blueprint_revision", "0")) + 1
        changed_history: list[str] = []
        for key, value in changes.items():
            heading = self.CHANGEABLE_SECTIONS[key]
            previous = _section_value(blueprint, heading)
            expected_hash = metadata.get(_hash_key(heading))
            if expected_hash and _content_hash(previous) != expected_hash:
                changed_history.append(
                    f"- Direct human edit detected in {heading} before revision {revision}; "
                    f"preserved content:\n\n```md\n{previous.rstrip()}\n```"
                )
            else:
                changed_history.append(f"- {heading} before revision {revision}: {previous}")
            rendered = _items(value) if isinstance(value, tuple) else value.strip()
            blueprint = _set_section(blueprint, heading, rendered)
        history = _section_value(blueprint, "Revision history")
        entry = (
            f"### Revision {revision}\n\n"
            f"Evidence/reasoning: {evidence_note.strip()}\n\n"
            + "\n".join(changed_history)
        )
        if history == "No revisions yet.":
            history = entry
        else:
            history = history.rstrip() + "\n\n" + entry
        blueprint = _set_section(blueprint, "Revision history", history)
        updates = {
            "blueprint_revision": str(revision),
            "blueprint_status": "ADAPTABLE",
            "frozen": "false",
            "updated": self.today.isoformat(),
        }
        for key in changes:
            heading = self.CHANGEABLE_SECTIONS[key]
            updates[_hash_key(heading)] = _content_hash(_section_value(blueprint, heading))
        blueprint = _replace_frontmatter(blueprint, updates)
        self.blueprint_path.write_text(blueprint.rstrip() + "\n", encoding="utf-8")
        return revision

    def _validate_proposal(self, proposal: BlueprintProposal) -> None:
        required_sequences = {
            "section_structure": proposal.section_structure,
            "comparison_dimensions": proposal.comparison_dimensions,
            "evidence_strategy": proposal.evidence_strategy,
            "target_journal_requirements": proposal.target_journal_requirements,
            "known_risks": proposal.known_risks,
            "candidate_units": proposal.candidate_units,
        }
        missing = [name for name, value in required_sequences.items() if not _nonblank(value)]
        if not proposal.narrative_line.strip():
            missing.append("narrative_line")
        if missing:
            raise ValueError("Blueprint proposal is missing: " + ", ".join(missing))


def _items(values: tuple[str, ...]) -> str:
    return "\n".join(f"- {value}" for value in values if value.strip()) or "- None recorded."


def _nonblank(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(value.strip() for value in values if value.strip())


def _literature_evidence_ids(literature: str) -> set[str]:
    """Extract complete evidence IDs from generated literature bullets.

    The delimiter is the first colon followed by a space, so URL schemes and
    colons inside an identifier remain part of the ID.
    """

    available: set[str] = set()
    for heading in ("Anchor/core", "Extension", "Background/definition", "Controversy"):
        for line in _section_value(literature, heading).splitlines():
            if not line.startswith("- "):
                continue
            entry = line[2:].strip()
            identifier, separator, _ = entry.partition(": ")
            if not separator:
                identifier = entry.split(":", 1)[0]
            if identifier.strip():
                available.add(identifier.strip())
    return available


def _render_signals(signals: tuple[PrototypeSignal, ...], kind: str) -> str:
    rendered = []
    for signal in signals:
        if signal.kind != kind:
            continue
        rendered.append(
            f"- {signal.statement.strip()}\n"
            f"  - Evidence: {', '.join(_nonblank(signal.evidence_ids))}\n"
            f"  - Value beyond summary: {signal.value_gain.strip()}"
        )
    return "\n".join(rendered) or "- None recorded."


def _selection_text(submission: PrototypeSubmission) -> str:
    if submission.paper_ids:
        return "Selected Research papers:\n" + _items(submission.paper_ids)
    return (
        f"Selected subsection: {submission.subsection.strip()}\n\n"
        "Bound Research evidence:\n"
        + _items(submission.subsection_evidence_ids)
    )


def _hash_key(title: str) -> str:
    normalized = "".join(
        character if character.isalnum() else "_" for character in title.lower()
    ).strip("_")
    return f"generated_{normalized}_sha256"


def _content_hash(value: str) -> str:
    normalized = value.strip().replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _record_generated_hashes(document: str, headings) -> str:
    updates = {heading: _content_hash(_section_value(document, heading)) for heading in headings}
    return _replace_frontmatter(document, {_hash_key(heading): value for heading, value in updates.items()})
