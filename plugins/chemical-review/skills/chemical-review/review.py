"""Multi-layer Review and synchronized dual-track delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
from pathlib import Path
import re
from typing import Callable, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from orchestrator import _document, _section_value, _split_frontmatter
from units import CLAIM_LEVELS, CONTRIBUTION_TYPES


INTEGRITY_KINDS = {
    "FABRICATED_OR_UNFINDABLE_SOURCE",
    "MISQUOTED_SOURCE_DATA",
    "INVENTED_CHEMICAL_FACT",
    "INFERENCE_AS_SOURCE_FACT",
}
JOURNAL_STATUSES = {"MET", "GAP", "NOT_APPLICABLE"}
VALUE_STATUSES = {"SUMMARY_ONLY", "VALUE_PRODUCING"}
VALUE_TYPES = {
    "comparison",
    "explanation",
    "rebuttal",
    "trend",
    "hypothesis",
    "new_research_question",
}


@dataclass(frozen=True)
class IntegrityFinding:
    """One narrow scientific-integrity failure reported by Review."""

    kind: str
    detail: str
    content_locator: str
    source_locator: str


@dataclass(frozen=True)
class JournalCandidate:
    """One target-journal option proposed before the researcher confirms it."""

    target_journal: str
    rationale: str
    official_guide_locator: str


@dataclass(frozen=True)
class JournalGuideSnapshot:
    """The exact public author-guide content read for journal adaptation."""

    target_journal: str
    source_locator: str
    content: str
    retrieved_at: str
    content_digest: str = ""

    def __post_init__(self) -> None:
        if not self.content_digest:
            object.__setattr__(
                self,
                "content_digest",
                hashlib.sha256(self.content.encode("utf-8")).hexdigest(),
            )


class JournalGuideFetcher(Protocol):
    def fetch(self, candidate: JournalCandidate) -> JournalGuideSnapshot: ...


class JournalGuideUnavailable(RuntimeError):
    """The selected journal's official guide could not be fetched."""


class HttpJournalGuideFetcher:
    """Read a public official author guide without storing credentials."""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        opener: Callable[..., object] | None = None,
    ) -> None:
        self.timeout = timeout
        self.opener = opener or urlopen

    def fetch(self, candidate: JournalCandidate) -> JournalGuideSnapshot:
        if not candidate.official_guide_locator.strip():
            raise ValueError("A journal candidate requires an official guide locator.")
        parsed_locator = urlparse(candidate.official_guide_locator.strip())
        if parsed_locator.scheme not in {"http", "https"} or not parsed_locator.netloc:
            raise ValueError("Official journal guide locators must be absolute HTTP(S) URLs.")
        request = Request(
            candidate.official_guide_locator,
            headers={"User-Agent": "chemical-review-skill/1.0"},
        )
        try:
            response = self.opener(request, timeout=self.timeout)
            with response as handle:
                raw = handle.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise JournalGuideUnavailable(
                f"Could not read the official guide for {candidate.target_journal}: {exc}"
            ) from exc
        content = raw.decode("utf-8", errors="replace").strip()
        if not content:
            raise JournalGuideUnavailable(
                f"The official guide for {candidate.target_journal} was empty."
            )
        return JournalGuideSnapshot(
            target_journal=candidate.target_journal.strip(),
            source_locator=candidate.official_guide_locator.strip(),
            content=content,
            retrieved_at=date.today().isoformat(),
        )


@dataclass(frozen=True)
class JournalRequirement:
    requirement: str
    status: str
    note: str
    source_locator: str


@dataclass(frozen=True)
class JournalAdaptation:
    target_journal: str
    requirements: tuple[JournalRequirement, ...]
    guide: JournalGuideSnapshot


@dataclass(frozen=True)
class ReviewAssessment:
    """Agent review judgments that cannot be inferred from strings alone."""

    value_status: str
    value_notes: tuple[str, ...]
    chemical_reasoning_notes: tuple[str, ...]
    intent_alignment_notes: tuple[str, ...]
    revision_requests: tuple[str, ...]
    nonblocking_uncertainties: tuple[str, ...]
    integrity_findings: tuple[IntegrityFinding, ...]


@dataclass(frozen=True)
class ReviewRunResult:
    package_status: str
    value_status: str
    integrity_status: str
    synchronization_status: str
    source_digest: str
    content_revision: int


@dataclass(frozen=True)
class _ContentBlock:
    section: str
    claim_level: str
    contribution_type: str
    source_units: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    text: str


class ReviewRunner:
    """Review one content revision and emit both views from the same blocks."""

    OUTPUT_NAMES = (
        "clean-manuscript.md",
        "researcher-review.md",
        "review-report.md",
        "submission-candidate-package.md",
    )
    REQUIRED_ASSET_KINDS = {
        "review-content.md": "single-review-content-source",
        "review-intent.md": "review-intent",
        "domain-profile.md": "domain-profile",
        "research-evidence.md": "research-evidence",
        "literature-set.md": "layered-literature-set",
        "review-blueprint.md": "review-blueprint",
        "unit-plan.md": "research-writing-unit-plan",
    }

    def __init__(self, project_root: str | Path, *, today: date | None = None) -> None:
        self.project_root = Path(project_root)
        self.today = today or date.today()

    def run(
        self,
        assessment: ReviewAssessment,
        journal: JournalAdaptation | None,
    ) -> ReviewRunResult:
        self._validate_inputs(assessment, journal)
        content_path = self.project_root / "review-content.md"
        intent_path = self.project_root / "review-intent.md"
        state_path = self.project_root / "workflow-state.md"
        for path in (content_path, intent_path, state_path):
            if not path.exists():
                raise FileNotFoundError(f"Review requires saved asset: {path.name}")
        existing = [name for name in self.OUTPUT_NAMES if (self.project_root / name).exists()]
        if existing:
            raise FileExistsError(
                "Review outputs already exist and will not be overwritten: " + ", ".join(existing)
            )
        included_assets = self._validate_candidate_assets(journal)

        content = content_path.read_text(encoding="utf-8")
        content_metadata, _ = _split_frontmatter(content)
        if content_metadata.get("kind") != "single-review-content-source":
            raise ValueError("review-content.md has the wrong asset kind.")
        blocks = _parse_content_blocks(content)
        content_revision = int(content_metadata.get("content_revision", "0"))
        source_digest = _source_digest(blocks, content_revision)
        value_types = tuple(
            dict.fromkeys(
                block.contribution_type
                for block in blocks
                if block.contribution_type in VALUE_TYPES
            )
        )
        value_status = assessment.value_status
        integrity_status = "HARD_STOP" if assessment.integrity_findings else "CLEAR"
        journal_gaps = tuple(
            requirement
            for requirement in (journal.requirements if journal else ())
            if requirement.status == "GAP"
        )
        if assessment.integrity_findings:
            package_status = "INTEGRITY_HOLD"
        elif (
            value_status == "SUMMARY_ONLY"
            or journal_gaps
            or _nonblank(assessment.revision_requests)
        ):
            package_status = "REVISION_REQUIRED"
        else:
            package_status = "SUBMISSION_CANDIDATE"

        intent = intent_path.read_text(encoding="utf-8")
        question = _section_value(intent, "Research question") or "Chemical Literature Review"
        workflow_state = state_path.read_text(encoding="utf-8")
        tool_degradation = _section_value(
            workflow_state, "Tool degradation or HUMAN_ACTION_REQUIRED"
        ) or "None recorded."
        outputs = {
            "clean-manuscript.md": self._clean_view(
                question,
                blocks,
                content_revision=content_revision,
                source_digest=source_digest,
                package_status=package_status,
            ),
            "researcher-review.md": self._researcher_view(
                question,
                blocks,
                content_revision=content_revision,
                source_digest=source_digest,
                package_status=package_status,
            ),
            "review-report.md": self._review_report(
                assessment,
                journal,
                value_status=value_status,
                value_types=value_types,
                integrity_status=integrity_status,
                package_status=package_status,
                content_revision=content_revision,
                source_digest=source_digest,
                tool_degradation=tool_degradation,
            ),
            "submission-candidate-package.md": self._package_manifest(
                assessment,
                journal,
                package_status=package_status,
                value_status=value_status,
                integrity_status=integrity_status,
                content_revision=content_revision,
                source_digest=source_digest,
                tool_degradation=tool_degradation,
                included_assets=included_assets,
            ),
        }
        written: list[Path] = []
        try:
            for name, text in outputs.items():
                path = self.project_root / name
                written.append(path)
                path.write_text(text.rstrip() + "\n", encoding="utf-8")
        except Exception:
            for path in written:
                path.unlink(missing_ok=True)
            raise
        return ReviewRunResult(
            package_status=package_status,
            value_status=value_status,
            integrity_status=integrity_status,
            synchronization_status="SYNCHRONIZED",
            source_digest=source_digest,
            content_revision=content_revision,
        )

    def _validate_candidate_assets(self, journal: JournalAdaptation | None) -> tuple[str, ...]:
        intent_text = (self.project_root / "review-intent.md").read_text(encoding="utf-8")
        intent_target = _intent_target_journal(intent_text)
        if intent_target and journal is None:
            raise ValueError(
                "The confirmed intent names a target journal; provide its fetched JournalAdaptation."
            )
        if intent_target and journal is not None and intent_target != journal.target_journal.strip():
            raise ValueError("JournalAdaptation does not match the confirmed target journal.")
        missing = [
            name
            for name in self.REQUIRED_ASSET_KINDS
            if not (self.project_root / name).exists()
        ]
        if missing:
            raise FileNotFoundError(
                "Submission candidate requires saved assets: " + ", ".join(missing)
            )
        assets: list[str] = []
        for name, expected_kind in self.REQUIRED_ASSET_KINDS.items():
            metadata, _ = _split_frontmatter(
                (self.project_root / name).read_text(encoding="utf-8")
            )
            if metadata.get("kind") != expected_kind:
                raise ValueError(
                    f"{name} has the wrong asset kind; expected {expected_kind}."
                )
            assets.append(name)
        optional_delivery_assets = {
            "source-registry.md": "research-source-registry",
            "coverage-matrix.md": "research-coverage-matrix",
            "figure-inventory.md": "figure-inventory",
        }
        for name, expected_kind in optional_delivery_assets.items():
            path = self.project_root / name
            if not path.exists():
                continue
            metadata, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
            if metadata.get("kind") != expected_kind:
                raise ValueError(
                    f"{name} has the wrong asset kind; expected {expected_kind}."
                )
            assets.append(name)
        for path in sorted(self.project_root.glob("*.docx.manifest.md")):
            metadata, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
            if metadata.get("kind") != "docx-export-manifest":
                raise ValueError(
                    f"{path.name} has the wrong asset kind; expected docx-export-manifest."
                )
            assets.append(str(path.relative_to(self.project_root)))
        unit_paths = tuple(sorted((self.project_root / "units").glob("*.md")))
        if not unit_paths:
            raise FileNotFoundError("Submission candidate requires at least one saved unit asset.")
        assets.extend(str(path.relative_to(self.project_root)) for path in unit_paths)
        if journal is not None:
            guide_path = self.project_root / "journal-guide.md"
            if not guide_path.exists():
                raise FileNotFoundError("Journal adaptation requires journal-guide.md.")
            guide_text = guide_path.read_text(encoding="utf-8")
            guide_metadata, _ = _split_frontmatter(guide_text)
            if any(
                guide_metadata.get(key, "") != value
                for key, value in {
                    "kind": "journal-guide-snapshot",
                    "target_journal": journal.target_journal,
                    "source_locator": journal.guide.source_locator,
                    "content_digest": journal.guide.content_digest,
                }.items()
            ):
                raise ValueError("journal-guide.md does not match the supplied JournalAdaptation.")
            guide_content = _section_value(guide_text, "Guide content")
            if hashlib.sha256(guide_content.encode("utf-8")).hexdigest() != journal.guide.content_digest:
                raise ValueError("journal-guide.md content digest does not match the supplied guide.")
            assets.append("journal-guide.md")
        return tuple(assets)

    def _validate_inputs(
        self, assessment: ReviewAssessment, journal: JournalAdaptation | None
    ) -> None:
        if assessment.value_status not in VALUE_STATUSES:
            raise ValueError("Unknown Review value status: " + assessment.value_status)
        if not _nonblank(assessment.value_notes):
            raise ValueError("Review requires an explicit value judgment and rationale.")
        if not _nonblank(assessment.chemical_reasoning_notes):
            raise ValueError("Review requires chemical-reasoning notes.")
        if not _nonblank(assessment.intent_alignment_notes):
            raise ValueError("Review requires intent-alignment notes.")
        for finding in assessment.integrity_findings:
            if finding.kind not in INTEGRITY_KINDS:
                raise ValueError("Unknown scientific-integrity finding: " + finding.kind)
            if not all(
                value.strip()
                for value in (
                    finding.detail,
                    finding.content_locator,
                    finding.source_locator,
                )
            ):
                raise ValueError("Scientific-integrity findings require detail and locators.")
        if journal is None:
            return
        if not journal.target_journal.strip() or not journal.requirements:
            raise ValueError("Journal adaptation requires a target and at least one requirement.")
        guide = journal.guide
        if guide.target_journal.strip() != journal.target_journal.strip():
            raise ValueError("Journal guide snapshot does not match the target journal.")
        if not guide.source_locator.strip() or not guide.content.strip():
            raise ValueError("Journal adaptation requires a non-empty official guide snapshot.")
        expected_digest = hashlib.sha256(guide.content.encode("utf-8")).hexdigest()
        if guide.content_digest != expected_digest:
            raise ValueError("Journal guide snapshot digest does not match its content.")
        for requirement in journal.requirements:
            if requirement.status not in JOURNAL_STATUSES:
                raise ValueError("Unknown journal-requirement status: " + requirement.status)
            if not all(
                value.strip()
                for value in (
                    requirement.requirement,
                    requirement.note,
                    requirement.source_locator,
                )
            ):
                raise ValueError("Journal requirements require a note and source locator.")

    def _clean_view(
        self,
        question: str,
        blocks: tuple[_ContentBlock, ...],
        *,
        content_revision: int,
        source_digest: str,
        package_status: str,
    ) -> str:
        metadata = {
            "kind": "clean-review-manuscript",
            "schema": "1",
            "source_content_revision": str(content_revision),
            "source_digest": source_digest,
            "delivery_status": package_status,
            "updated": self.today.isoformat(),
        }
        body = f"# {question}\n\n" + _render_clean_sections(blocks)
        return _document(metadata, body)

    def _researcher_view(
        self,
        question: str,
        blocks: tuple[_ContentBlock, ...],
        *,
        content_revision: int,
        source_digest: str,
        package_status: str,
    ) -> str:
        metadata = {
            "kind": "researcher-review-view",
            "schema": "1",
            "source_content_revision": str(content_revision),
            "source_digest": source_digest,
            "delivery_status": package_status,
            "updated": self.today.isoformat(),
        }
        body = (
            f"# Researcher Review View: {question}\n\n"
            "Annotations apply to key content blocks, not every sentence.\n\n"
            + _render_researcher_sections(blocks)
        )
        return _document(metadata, body)

    def _review_report(
        self,
        assessment: ReviewAssessment,
        journal: JournalAdaptation | None,
        *,
        value_status: str,
        value_types: tuple[str, ...],
        integrity_status: str,
        package_status: str,
        content_revision: int,
        source_digest: str,
        tool_degradation: str,
    ) -> str:
        metadata = {
            "kind": "multi-layer-review-report",
            "schema": "1",
            "package_status": package_status,
            "value_status": value_status,
            "integrity_status": integrity_status,
            "synchronization_status": "SYNCHRONIZED",
            "source_content_revision": str(content_revision),
            "source_digest": source_digest,
            "updated": self.today.isoformat(),
        }
        declared_modes = (
            "Declared contribution modes in the content source: " + ", ".join(value_types) + "."
            if value_types
            else "No value-producing contribution mode is declared in the content source."
        )
        summary_note = (
            "\n\nNo comparison, explanation, rebuttal, trend, or a new hypothesis/question "
            "survived Review; fluent summary requires revision."
            if value_status == "SUMMARY_ONLY"
            else ""
        )
        body = (
            "# Multi-layer Review Report\n\n"
            "## Review value\n"
            f"Status: {value_status}\n\n"
            f"{_items(assessment.value_notes)}\n\n"
            f"{declared_modes}{summary_note}\n\n"
            "## Chemical reasoning\n"
            f"{_items(assessment.chemical_reasoning_notes)}\n\n"
            "## Scientific integrity\n"
            f"Status: {integrity_status}\n\n"
            f"{_integrity_items(assessment.integrity_findings)}\n\n"
            "## Intent alignment\n"
            f"{_items(assessment.intent_alignment_notes)}\n\n"
            "## Journal adaptation\n"
            f"{_journal_section(journal)}\n\n"
            "## Synchronization\n"
            "Status: SYNCHRONIZED\n\n"
            f"Both views were generated from content revision {content_revision} and digest {source_digest}.\n\n"
            "## Non-blocking uncertainties\n"
            f"{_tagged_items(assessment.nonblocking_uncertainties, 'NON_BLOCKING')}\n\n"
            "## Revision requests\n"
            f"{_items(assessment.revision_requests)}\n\n"
            "## Tool degradation or HUMAN_ACTION_REQUIRED\n"
            f"{tool_degradation}\n\n"
            "## Human notes\n"
        )
        return _document(metadata, body)

    def _package_manifest(
        self,
        assessment: ReviewAssessment,
        journal: JournalAdaptation | None,
        *,
        package_status: str,
        value_status: str,
        integrity_status: str,
        content_revision: int,
        source_digest: str,
        tool_degradation: str,
        included_assets: Sequence[str],
    ) -> str:
        metadata = {
            "kind": "submission-candidate-package",
            "schema": "1",
            "package_status": package_status,
            "source_content_revision": str(content_revision),
            "source_digest": source_digest,
            "updated": self.today.isoformat(),
        }
        unresolved = (
            tuple(assessment.revision_requests)
            + tuple(assessment.nonblocking_uncertainties)
            + tuple(
                requirement.note
                for requirement in (journal.requirements if journal else ())
                if requirement.status == "GAP"
            )
        )
        body = (
            "# Submission-candidate Package\n\n"
            "## Candidate state\n"
            f"{package_status}\n\n"
            f"Value: {value_status}; scientific integrity: {integrity_status}; views: SYNCHRONIZED.\n\n"
            "## Included assets\n"
            + "\n".join(f"- {asset}" for asset in included_assets)
            + "\n"
            "- clean-manuscript.md\n"
            "- researcher-review.md\n"
            "- review-report.md\n\n"
            "## Target-journal state\n"
            f"{_journal_target_state(journal)}\n\n"
            "## Unresolved questions and next review inputs\n"
            f"{_items(unresolved)}\n\n"
            "## Tool degradation or HUMAN_ACTION_REQUIRED\n"
            f"{tool_degradation}\n\n"
            "## Boundary\n"
            "This package does not claim scientific validity or journal acceptance. "
            "The human science editor retains final acceptance, modification, and submission authority.\n"
        )
        return _document(metadata, body)


def _parse_content_blocks(content: str) -> tuple[_ContentBlock, ...]:
    section = _section_value(content, "Content blocks")
    blocks: list[_ContentBlock] = []
    pattern = re.compile(
        r"^### Merge .*?\n(.*?)(?=^### Merge .*?\n|\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    matches = tuple(pattern.finditer(section))
    if pattern.sub("", section).strip():
        raise ValueError(
            "review-content.md contains content outside structured merge blocks."
        )
    for match in matches:
        raw = match.group(1)
        text_match = re.search(r"^Text:\n(.*)\Z", raw, flags=re.MULTILINE | re.DOTALL)
        if not text_match:
            raise ValueError("review-content.md contains a malformed content block.")
        block = _ContentBlock(
            section=_field(raw, "Section"),
            claim_level=_field(raw, "Claim level"),
            contribution_type=_field(raw, "Contribution type"),
            source_units=_csv(_field(raw, "Source units")),
            evidence_ids=_csv(_field(raw, "Evidence IDs")),
            text=text_match.group(1).strip(),
        )
        if block.claim_level not in CLAIM_LEVELS:
            raise ValueError("Unknown claim level in review-content.md: " + block.claim_level)
        if block.contribution_type not in CONTRIBUTION_TYPES:
            raise ValueError(
                "Unknown contribution type in review-content.md: " + block.contribution_type
            )
        if not block.section or not block.text:
            raise ValueError("Content blocks require a section and text.")
        blocks.append(block)
    if not blocks:
        raise ValueError("review-content.md contains no structured content blocks.")
    return tuple(blocks)


def _render_clean_sections(blocks: tuple[_ContentBlock, ...]) -> str:
    sections: dict[str, list[str]] = {}
    for block in blocks:
        sections.setdefault(block.section, []).append(block.text)
    if not sections:
        return "No review content has been merged yet."
    return "\n\n".join(
        f"## {section}\n\n" + "\n\n".join(texts)
        for section, texts in sections.items()
    )


def _render_researcher_sections(blocks: tuple[_ContentBlock, ...]) -> str:
    sections: dict[str, list[_ContentBlock]] = {}
    for block in blocks:
        sections.setdefault(block.section, []).append(block)
    if not sections:
        return "No review content has been merged yet."
    rendered_sections = []
    for section, values in sections.items():
        rendered_blocks = []
        for index, block in enumerate(values, start=1):
            rendered_blocks.append(
                f"### Key claim {index}\n\n"
                f"- Claim level: `{block.claim_level}`\n"
                f"- Contribution: `{block.contribution_type}`\n"
                f"- Evidence IDs: {', '.join(block.evidence_ids) or 'None recorded.'}\n"
                f"- Source units: {', '.join(block.source_units) or 'None recorded.'}\n\n"
                f"{block.text}"
            )
        rendered_sections.append(f"## {section}\n\n" + "\n\n".join(rendered_blocks))
    return "\n\n".join(rendered_sections)


def _source_digest(blocks: tuple[_ContentBlock, ...], content_revision: int) -> str:
    values = [f"revision={content_revision}"]
    for block in blocks:
        values.extend(
            (
                block.section,
                block.claim_level,
                block.contribution_type,
                ",".join(block.source_units),
                ",".join(block.evidence_ids),
                block.text,
            )
        )
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _field(block: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.*)$", block, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _csv(value: str) -> tuple[str, ...]:
    if value in {"", "NONE", "None recorded."}:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _items(values: Sequence[str]) -> str:
    return "\n".join(f"- {value.strip()}" for value in values if value.strip()) or "- None recorded."


def _tagged_items(values: Sequence[str], tag: str) -> str:
    return "\n".join(f"- [{tag}] {value.strip()}" for value in values if value.strip()) or "- None recorded."


def _integrity_items(findings: Sequence[IntegrityFinding]) -> str:
    return "\n".join(
        f"- [HARD_STOP] {finding.kind}: {finding.detail} "
        f"(content: {finding.content_locator}; source: {finding.source_locator})"
        for finding in findings
    ) or "- No narrow scientific-integrity hard stop was reported."


def _journal_items(requirements: Sequence[JournalRequirement]) -> str:
    return "\n".join(
        f"- [{requirement.status}] {requirement.requirement}: {requirement.note} "
        f"(official source: {requirement.source_locator})"
        for requirement in requirements
    )


def _journal_section(journal: JournalAdaptation | None) -> str:
    if journal is None:
        return (
            "Target journal: NOT_SELECTED\n\n"
            "Journal adaptation: NOT_APPLICABLE because the confirmed intent targets a reader, "
            "not a specific journal."
        )
    guide = journal.guide
    return (
        f"Target journal: {journal.target_journal}\n\n"
        f"{_journal_items(journal.requirements)}\n\n"
        f"Official guide snapshot: {guide.source_locator}; retrieved {guide.retrieved_at}; "
        f"digest {guide.content_digest}\n\n"
        "Journal adaptation is not a prediction of journal acceptance."
    )


def _journal_target_state(journal: JournalAdaptation | None) -> str:
    if journal is None:
        return "No target journal selected; reader-facing delivery only. Journal adaptation is NOT_APPLICABLE."
    guide = journal.guide
    return (
        f"{journal.target_journal}; official guide snapshot {guide.source_locator} "
        f"(digest {guide.content_digest}); formatting readiness is not a prediction of journal acceptance."
    )


def _intent_target_journal(intent: str) -> str:
    metadata, _ = _split_frontmatter(intent)
    if metadata.get("target_journal", "").strip():
        return metadata["target_journal"].strip()
    audience = _section_value(intent, "Audience or target journal")
    match = re.search(r"(?:^|\n)Target journal:\s*(.+)$", audience, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _nonblank(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(value.strip() for value in values if value.strip())
