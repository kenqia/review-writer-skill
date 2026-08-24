"""Dependency-aware research/writing units and central content merge."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from graphlib import CycleError, TopologicalSorter
import hashlib
from pathlib import Path
import re
from typing import Mapping, Sequence

from orchestrator import (
    _document,
    _replace_frontmatter,
    _section_value,
    _set_section,
    _split_frontmatter,
)


CLAIM_LEVELS = {"SOURCE_FACT", "MODEL_SYNTHESIS", "MODEL_HYPOTHESIS"}
COMPARABILITY_STATUSES = {"COMPARABLE", "NOT_COMPARABLE", "GAP", "NOT_APPLICABLE"}
CONTRIBUTION_TYPES = {
    "term_verification",
    "retrieval",
    "comparison",
    "explanation",
    "rebuttal",
    "trend",
    "hypothesis",
    "new_research_question",
    "section_draft",
}
UNIT_STATUSES = {"PENDING", "READY", "BLOCKED", "COMPLETE", "MERGED"}
UNIT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class MergeHistoryEditConflict(ValueError):
    """Raised when edited merge history cannot be trusted for recovery."""


@dataclass(frozen=True)
class ResearchWritingUnit:
    """One independently executable unit derived from the review blueprint."""

    unit_id: str
    kind: str
    purpose: str
    prerequisites: tuple[str, ...]
    completion_signal: str
    remaining_uncertainty: str


@dataclass(frozen=True)
class ClaimBlock:
    """One claim-level contribution proposed by a completed unit."""

    section: str
    claim_level: str
    contribution_type: str
    text: str
    evidence_ids: tuple[str, ...] = ()
    comparability_status: str = "NOT_APPLICABLE"
    comparability_basis: str = ""


@dataclass(frozen=True)
class UnitResult:
    """A unit-local result; it cannot mutate the central content source."""

    unit_id: str
    completion_evidence: str
    findings: tuple[str, ...]
    claims: tuple[ClaimBlock, ...]
    remaining_uncertainty: str
    tool_degradation: str = ""
    human_action_required: str = ""


@dataclass(frozen=True)
class MergeResolution:
    """Central resolution for claims from multiple units targeting one section."""

    section: str
    text: str
    claim_level: str
    contribution_type: str
    evidence_ids: tuple[str, ...]
    rationale: str
    comparability_status: str = "NOT_APPLICABLE"
    comparability_basis: str = ""


@dataclass(frozen=True)
class UnitSubmitResult:
    unit_status: str
    ready_ids: tuple[str, ...]
    all_results_complete: bool
    blocked_ids: tuple[str, ...]
    tool_degradation: str
    human_action_required: str


@dataclass(frozen=True)
class UnitMergeResult:
    status: str
    conflicts: tuple[str, ...]
    merged_ids: tuple[str, ...]
    all_units_merged: bool
    content_revision: int | None
    human_edit_detected: bool
    readiness: str = "DISCOVERY_READY"
    content_digest: str = ""


class UnitManager:
    """Persist a small dependency graph and merge only through one owner."""

    def __init__(self, project_root: str | Path, *, today: date | None = None) -> None:
        self.project_root = Path(project_root)
        self.today = today or date.today()

    @property
    def plan_path(self) -> Path:
        return self.project_root / "unit-plan.md"

    @property
    def unit_dir(self) -> Path:
        return self.project_root / "units"

    @property
    def content_path(self) -> Path:
        return self.project_root / "review-content.md"

    @property
    def merge_review_path(self) -> Path:
        return self.project_root / "merge-review.md"

    def create_plan(self, units: Sequence[ResearchWritingUnit]) -> tuple[str, ...]:
        if self.plan_path.exists():
            raise FileExistsError("unit-plan.md exists; preserve or revise it instead of overwriting it.")
        if not (self.project_root / "review-blueprint.md").exists():
            raise FileNotFoundError("Issues requires a saved review-blueprint.md.")
        validated = self._validate_units(units)
        self.unit_dir.mkdir(parents=False, exist_ok=False)
        try:
            for unit in validated:
                status = "READY" if not unit.prerequisites else "PENDING"
                self._write_unit(unit, status=status)
            blueprint = (self.project_root / "review-blueprint.md").read_text(encoding="utf-8")
            blueprint_meta, _ = _split_frontmatter(blueprint)
            metadata = {
                "kind": "research-writing-unit-plan",
                "schema": "1",
                "status": "READY_FOR_ACCEPTANCE",
                "blueprint_revision": blueprint_meta.get("blueprint_revision", "0"),
                "unit_count": str(len(validated)),
                "updated": self.today.isoformat(),
            }
            unit_lines = "\n".join(
                f"- {unit.unit_id} ({unit.kind}); prerequisites: "
                + (", ".join(unit.prerequisites) if unit.prerequisites else "none")
                for unit in validated
            )
            ready = tuple(unit.unit_id for unit in validated if not unit.prerequisites)
            body = (
                "# Research/Writing Unit Plan\n\n"
                "Units are independently writable assets. Only the orchestrator merges accepted results "
                "into review-content.md.\n\n"
                "## Blueprint basis\n"
                f"review-blueprint.md revision {metadata['blueprint_revision']}\n\n"
                "## Units\n"
                f"{unit_lines}\n\n"
                "## Initially parallel-ready\n"
                f"{_items(ready)}\n\n"
                "## Human notes\n"
            )
            self.plan_path.write_text(
                _document(metadata, body).rstrip() + "\n", encoding="utf-8"
            )
        except Exception:
            self.plan_path.unlink(missing_ok=True)
            for unit in validated:
                self._unit_path(unit.unit_id).unlink(missing_ok=True)
            self.unit_dir.rmdir()
            raise
        return ready

    def ready_unit_ids(self) -> tuple[str, ...]:
        self._require_plan()
        statuses = self._statuses()
        return tuple(
            unit_id
            for unit_id in self._plan_unit_ids()
            if statuses[unit_id] == "READY"
            and all(
                statuses[dependency] in {"COMPLETE", "MERGED"}
                for dependency in self._unit_prerequisites(unit_id)
            )
        )

    def unit_ids(self) -> tuple[str, ...]:
        """Return declared units in plan order for batch execution."""

        self._require_plan()
        return self._plan_unit_ids()

    def unit_status(self, unit_id: str) -> str:
        """Expose a read-only status projection for resumable batches."""

        self._require_plan()
        if unit_id not in self._plan_unit_ids():
            raise ValueError(f"Unknown research/writing unit: {unit_id}")
        return self._unit_status(unit_id)

    def completed_unit_ids(self) -> tuple[str, ...]:
        """Return units whose local result is complete or centrally merged."""

        self._require_plan()
        return tuple(
            unit_id
            for unit_id in self._plan_unit_ids()
            if self._unit_status(unit_id) in {"COMPLETE", "MERGED"}
        )

    def submit_result(self, result: UnitResult) -> UnitSubmitResult:
        self._require_plan()
        if result.unit_id not in self._plan_unit_ids():
            raise ValueError(f"Unit {result.unit_id} is not declared by unit-plan.md.")
        unit_path = self._unit_path(result.unit_id)
        if not unit_path.exists():
            raise ValueError(f"Unknown research/writing unit: {result.unit_id}")
        incomplete = [
            dependency
            for dependency in self._unit_prerequisites(result.unit_id)
            if self._unit_status(dependency) not in {"COMPLETE", "MERGED"}
        ]
        if incomplete:
            raise ValueError(
                f"Unit {result.unit_id} is not ready; prerequisites are incomplete: "
                + ", ".join(incomplete)
            )
        if self._unit_status(result.unit_id) != "READY":
            raise ValueError(f"Unit {result.unit_id} is not ready; complete its prerequisites first.")
        if not result.remaining_uncertainty.strip():
            raise ValueError("Unit result must report remaining uncertainty.")

        if result.human_action_required.strip():
            status = "BLOCKED"
        else:
            if not result.completion_evidence.strip():
                raise ValueError("Completed unit result requires completion evidence.")
            if not _nonblank(result.findings) and not result.claims:
                raise ValueError("Completed unit result requires findings or claim blocks.")
            available_evidence = self._available_evidence_records()
            result = replace(
                result,
                claims=tuple(_normalize_claim(claim) for claim in result.claims),
            )
            for claim in result.claims:
                _validate_claim(claim, available_evidence=available_evidence)
            status = "COMPLETE"

        self._store_result(result, status=status)
        if status == "COMPLETE":
            self._refresh_ready_units()
        statuses = self._statuses()
        return UnitSubmitResult(
            unit_status=status,
            ready_ids=self.ready_unit_ids(),
            all_results_complete=all(value in {"COMPLETE", "MERGED"} for value in statuses.values()),
            blocked_ids=tuple(
                unit_id for unit_id in self._plan_unit_ids() if statuses[unit_id] == "BLOCKED"
            ),
            tool_degradation=result.tool_degradation.strip(),
            human_action_required=result.human_action_required.strip(),
        )

    def retry_unit(self, unit_id: str) -> tuple[str, ...]:
        self._require_plan()
        if self._unit_status(unit_id) != "BLOCKED":
            raise ValueError(f"Unit {unit_id} is not blocked and cannot be retried.")
        prerequisites = self._unit_prerequisites(unit_id)
        incomplete = [
            item for item in prerequisites if self._unit_status(item) not in {"COMPLETE", "MERGED"}
        ]
        if incomplete:
            raise ValueError("Unit prerequisites remain incomplete: " + ", ".join(incomplete))
        self._update_unit_metadata(unit_id, {"status": "READY", "updated": self.today.isoformat()})
        return self.ready_unit_ids()

    def merge(
        self,
        unit_ids: Sequence[str],
        *,
        conflict_sections: Sequence[str] = (),
        resolutions: Sequence[MergeResolution] = (),
    ) -> UnitMergeResult:
        self._require_plan()
        requested = tuple(dict.fromkeys(unit_ids))
        if not requested:
            raise ValueError("Central merge requires at least one completed unit.")
        plan_order = self._plan_unit_ids()
        unknown = set(requested) - set(plan_order)
        if unknown:
            raise ValueError("Unknown research/writing units: " + ", ".join(sorted(unknown)))
        selected = tuple(unit_id for unit_id in plan_order if unit_id in set(requested))
        selected_statuses = {unit_id: self._unit_status(unit_id) for unit_id in selected}
        for unit_id, status in selected_statuses.items():
            if status not in {"COMPLETE", "MERGED"}:
                raise ValueError(f"Unit {unit_id} is not complete.")
        recorded_units = self._recorded_merged_unit_ids()
        for unit_id, status in selected_statuses.items():
            if status == "COMPLETE" and unit_id in recorded_units:
                self._update_unit_metadata(
                    unit_id, {"status": "MERGED", "updated": self.today.isoformat()}
                )
                selected_statuses[unit_id] = "MERGED"
        recovery_only = all(status == "MERGED" for status in selected_statuses.values())

        claims_by_section: dict[str, list[tuple[str, ClaimBlock]]] = {}
        for unit_id in selected:
            for claim in self._read_claims(unit_id):
                claims_by_section.setdefault(claim.section, []).append((unit_id, claim))
        multi_source_sections = {
            section
            for section, claims in claims_by_section.items()
            if len({unit_id for unit_id, _ in claims}) > 1
        }
        conflicts = tuple(dict.fromkeys(section.strip() for section in conflict_sections if section.strip()))
        invalid_conflicts = set(conflicts) - multi_source_sections
        if invalid_conflicts:
            raise ValueError(
                "Declared merge conflict is not shared by multiple units: "
                + ", ".join(sorted(invalid_conflicts))
            )
        resolution_map = {resolution.section: resolution for resolution in resolutions}
        if len(resolution_map) != len(tuple(resolutions)):
            raise ValueError("Merge resolutions must target unique sections.")
        unknown_resolutions = set(resolution_map) - set(conflicts)
        if unknown_resolutions:
            raise ValueError("Merge resolution has no matching conflict: " + ", ".join(sorted(unknown_resolutions)))
        unresolved = tuple(section for section in conflicts if section not in resolution_map)
        if unresolved:
            if any(status == "MERGED" for status in selected_statuses.values()):
                raise ValueError("A previously merged unit cannot enter a new unresolved conflict.")
            self._write_merge_review(selected, claims_by_section, unresolved, resolutions=())
            return UnitMergeResult(
                status="CONFLICT",
                conflicts=unresolved,
                merged_ids=(),
                all_units_merged=False,
                content_revision=None,
                human_edit_detected=False,
                readiness=self._current_readiness(),
            )

        merged_blocks: list[tuple[tuple[str, ...], ClaimBlock]] = []
        for section, claims in claims_by_section.items():
            source_units = tuple(dict.fromkeys(unit_id for unit_id, _ in claims))
            if section in resolution_map:
                resolution = resolution_map[section]
                if not resolution.rationale.strip():
                    raise ValueError("Merge resolution requires a rationale.")
                claim = ClaimBlock(
                    section=resolution.section,
                    claim_level=resolution.claim_level,
                    contribution_type=resolution.contribution_type,
                    text=resolution.text,
                    evidence_ids=tuple(
                        _canonical_evidence_id(item) for item in resolution.evidence_ids
                    ),
                    comparability_status=resolution.comparability_status,
                    comparability_basis=resolution.comparability_basis,
                )
                _validate_claim(claim, available_evidence=self._available_evidence_records())
                merged_blocks.append((source_units, claim))
            else:
                merged_blocks.extend(((unit_id,), claim) for unit_id, claim in claims)

        if recovery_only:
            if conflicts:
                self._write_merge_review(selected, claims_by_section, (), resolutions=resolutions)
            statuses = self._statuses()
            return UnitMergeResult(
                status="MERGED",
                conflicts=(),
                merged_ids=selected,
                all_units_merged=all(value == "MERGED" for value in statuses.values()),
                content_revision=self._current_content_revision(),
                human_edit_detected=False,
                readiness=self._current_readiness(),
                content_digest=self._content_digest(),
            )

        merge_key = _merge_key(selected, merged_blocks)
        already_recorded = self._content_has_merge_key(merge_key)
        if any(status == "MERGED" for status in selected_statuses.values()) and not already_recorded:
            raise ValueError("A merged unit cannot be reused in a different central merge.")
        revision, human_edit_detected = self._append_content(
            selected, merged_blocks, merge_key=merge_key
        )
        for unit_id, status in selected_statuses.items():
            if status == "COMPLETE":
                self._update_unit_metadata(
                    unit_id, {"status": "MERGED", "updated": self.today.isoformat()}
                )
        if conflicts:
            self._write_merge_review(selected, claims_by_section, (), resolutions=resolutions)
        statuses = self._statuses()
        return UnitMergeResult(
            status="MERGED",
            conflicts=(),
            merged_ids=selected,
            all_units_merged=all(value == "MERGED" for value in statuses.values()),
            content_revision=revision,
            human_edit_detected=human_edit_detected,
            readiness=(
                "CLAIM_READY"
                if merged_blocks and all(_claim_is_ready(claim) for _, claim in merged_blocks)
                else self._best_preclaim_readiness(merged_blocks)
            ),
            content_digest=self._content_digest(),
        )

    def _validate_units(
        self, units: Sequence[ResearchWritingUnit]
    ) -> tuple[ResearchWritingUnit, ...]:
        validated = tuple(units)
        if not validated:
            raise ValueError("Issues requires at least one research/writing unit.")
        ids = [unit.unit_id for unit in validated]
        if len(set(ids)) != len(ids):
            raise ValueError("Research/writing unit IDs must be unique.")
        for unit in validated:
            if not UNIT_ID_PATTERN.fullmatch(unit.unit_id):
                raise ValueError("Unit IDs use lowercase letters, digits, and hyphens only.")
            if not all(
                value.strip()
                for value in (
                    unit.kind,
                    unit.purpose,
                    unit.completion_signal,
                    unit.remaining_uncertainty,
                )
            ):
                raise ValueError(f"Unit {unit.unit_id} is missing its purpose, signal, or uncertainty.")
            unknown = set(unit.prerequisites) - set(ids)
            if unknown:
                raise ValueError(
                    f"Unit {unit.unit_id} has unknown prerequisites: " + ", ".join(sorted(unknown))
                )
        graph = {unit.unit_id: set(unit.prerequisites) for unit in validated}
        # Python 3.13 documents prepare() as the cycle-validation step for a dependency graph.
        # Source: https://docs.python.org/3.13/library/graphlib.html#graphlib.TopologicalSorter.prepare
        try:
            TopologicalSorter(graph).prepare()
        except CycleError as error:
            raise ValueError("Research/writing unit dependencies must be acyclic.") from error
        return validated

    def _write_unit(self, unit: ResearchWritingUnit, *, status: str) -> None:
        metadata = {
            "kind": "research-writing-unit",
            "schema": "1",
            "unit_id": unit.unit_id,
            "unit_kind": unit.kind,
            "status": status,
            "prerequisites": ", ".join(unit.prerequisites) if unit.prerequisites else "NONE",
            "updated": self.today.isoformat(),
        }
        body = (
            f"# Research/Writing Unit: {unit.unit_id}\n\n"
            "## Purpose\n"
            f"{unit.purpose}\n\n"
            "## Prerequisites\n"
            f"{_items(unit.prerequisites)}\n\n"
            "## Completion signal\n"
            f"{unit.completion_signal}\n\n"
            "## Remaining uncertainty\n"
            f"{unit.remaining_uncertainty}\n\n"
            "## Latest result\n\n"
            "## Result history\n"
            "No earlier result.\n\n"
            "## Preserved human edits and conflicts\n\n"
            "## Human notes\n"
        )
        self._unit_path(unit.unit_id).write_text(
            _document(metadata, body).rstrip() + "\n", encoding="utf-8"
        )

    def _store_result(self, result: UnitResult, *, status: str) -> None:
        path = self._unit_path(result.unit_id)
        text = path.read_text(encoding="utf-8")
        metadata, _ = _split_frontmatter(text)
        previous = _section_value(text, "Latest result")
        history = _section_value(text, "Result history")
        preserved = _section_value(text, "Preserved human edits and conflicts")
        expected_hash = metadata.get("generated_latest_result_sha256")
        if expected_hash and _content_hash(previous) != expected_hash:
            conflict = (
                "### Preserved direct edit from Latest result\n\n"
                "The human-edited unit result was retained before retry:\n\n"
                f"```md\n{previous.rstrip()}\n```"
            )
            preserved = (preserved.rstrip() + "\n\n" + conflict).strip()
        if previous:
            entry = (
                f"### Previous {metadata.get('status', 'UNKNOWN')} result\n\n"
                f"{previous}"
            )
            history = entry if history == "No earlier result." else history.rstrip() + "\n\n" + entry
        rendered = _render_result(result)
        text = _set_section(text, "Latest result", rendered)
        text = _set_section(text, "Result history", history)
        text = _set_section(text, "Preserved human edits and conflicts", preserved)
        text = _replace_frontmatter(
            text,
            {
                "status": status,
                "updated": self.today.isoformat(),
                "generated_latest_result_sha256": _content_hash(rendered),
            },
        )
        path.write_text(text.rstrip() + "\n", encoding="utf-8")

    def _refresh_ready_units(self) -> None:
        changed = True
        while changed:
            changed = False
            statuses = self._statuses()
            for unit_id in self._plan_unit_ids():
                if statuses[unit_id] != "PENDING":
                    continue
                if all(
                    statuses[dependency] in {"COMPLETE", "MERGED"}
                    for dependency in self._unit_prerequisites(unit_id)
                ):
                    self._update_unit_metadata(
                        unit_id, {"status": "READY", "updated": self.today.isoformat()}
                    )
                    changed = True

    def _append_content(
        self,
        unit_ids: tuple[str, ...],
        blocks: Sequence[tuple[tuple[str, ...], ClaimBlock]],
        *,
        merge_key: str,
    ) -> tuple[int, bool]:
        if self.content_path.exists():
            content = self.content_path.read_text(encoding="utf-8")
            metadata, _ = _split_frontmatter(content)
            revision = int(metadata.get("content_revision", "0")) + 1
            current_readiness = metadata.get("readiness", "DISCOVERY_READY")
            existing_blocks = _section_value(content, "Content blocks")
            history = _section_value(content, "Merge history")
            preserved = _section_value(content, "Preserved human edits and conflicts")
            expected_hash = metadata.get("generated_content_blocks_sha256")
            human_edit_detected = bool(
                expected_hash and _content_hash(existing_blocks) != expected_hash
            )
            if human_edit_detected:
                conflict = (
                    f"### Direct human edit detected before merge {revision}\n\n"
                    "The edited Content blocks remain in place and were treated as merge input:\n\n"
                    f"```md\n{existing_blocks.rstrip()}\n```"
                )
                preserved = (preserved.rstrip() + "\n\n" + conflict).strip()
            if f"Merge key: {merge_key}" in history:
                if human_edit_detected:
                    content = _set_section(content, "Preserved human edits and conflicts", preserved)
                    content = _replace_frontmatter(
                        content,
                        {
                            "generated_content_blocks_sha256": _content_hash(existing_blocks),
                            "updated": self.today.isoformat(),
                        },
                    )
                    self.content_path.write_text(content.rstrip() + "\n", encoding="utf-8")
                return int(metadata.get("content_revision", "0")), human_edit_detected
        else:
            revision = 0
            current_readiness = "DISCOVERY_READY"
            existing_blocks = ""
            history = ""
            preserved = ""
            human_edit_detected = False
            content = _document(
                {
                    "kind": "single-review-content-source",
                    "schema": "1",
                    "content_revision": "0",
                    "status": "ACTIVE",
                    "updated": self.today.isoformat(),
                },
                "# Review Content Source\n\n"
                "This is the single source for later clean and researcher views. Unit workers cannot write it.\n\n"
                "## Content blocks\n\n"
                "## Merge history\n\n"
                "## Preserved human edits and conflicts\n\n"
                "## Human notes\n",
            )
        rendered = _render_content_blocks(revision, blocks)
        merged_content = (existing_blocks.rstrip() + "\n\n" + rendered).strip()
        history_entry = (
            f"### Merge {revision}\n\n"
            f"Accepted units: {', '.join(unit_ids)}\n\n"
            f"Merge key: {merge_key}\n\n"
            f"Blocks added: {len(blocks)}"
        )
        history = (history.rstrip() + "\n\n" + history_entry).strip()
        content = _set_section(content, "Content blocks", merged_content)
        content = _set_section(content, "Merge history", history)
        content = _set_section(content, "Preserved human edits and conflicts", preserved)
        merged_readiness = (
            "CLAIM_READY"
            if blocks and all(_claim_is_ready(claim) for _, claim in blocks)
            else self._best_preclaim_readiness(blocks)
        )
        content = _replace_frontmatter(
            content,
                {
                    "content_revision": str(revision),
                    "status": "ACTIVE",
                    "readiness": merged_readiness if blocks else current_readiness,
                    "generated_content_blocks_sha256": _content_hash(merged_content),
                "generated_merge_history_sha256": _content_hash(history),
                "updated": self.today.isoformat(),
            },
        )
        self.content_path.write_text(content.rstrip() + "\n", encoding="utf-8")
        return revision, human_edit_detected

    def _write_merge_review(
        self,
        unit_ids: tuple[str, ...],
        claims_by_section: Mapping[str, Sequence[tuple[str, ClaimBlock]]],
        conflicts: tuple[str, ...],
        *,
        resolutions: Sequence[MergeResolution],
    ) -> None:
        previous_notes = ""
        preserved = ""
        if self.merge_review_path.exists():
            previous = self.merge_review_path.read_text(encoding="utf-8")
            previous_metadata, _ = _split_frontmatter(previous)
            previous_notes = _section_value(previous, "Human notes")
            preserved = _section_value(previous, "Preserved human edits and conflicts")
            for heading in ("Selected units", "Conflicting sections", "Accepted resolutions"):
                previous_value = _section_value(previous, heading)
                expected_hash = previous_metadata.get(_merge_review_hash_key(heading))
                if expected_hash and _content_hash(previous_value) != expected_hash:
                    conflict = (
                        f"### Preserved direct edit from {heading}\n\n"
                        "The edited central-merge section was retained before regeneration:\n\n"
                        f"```md\n{previous_value.rstrip()}\n```"
                    )
                    if conflict not in preserved:
                        preserved = (preserved.rstrip() + "\n\n" + conflict).strip()
        status = "CONFLICT" if conflicts else "RESOLVED"
        conflict_sections = []
        for section in conflicts:
            claims = claims_by_section[section]
            conflict_sections.append(
                f"### {section}\n\n"
                f"Units: {', '.join(dict.fromkeys(unit_id for unit_id, _ in claims))}\n\n"
                + "\n\n".join(
                    f"- {unit_id} [{claim.claim_level}/{claim.contribution_type}]: {claim.text}"
                    for unit_id, claim in claims
                )
            )
        resolution_sections = "\n\n".join(
            f"### {resolution.section}\n\n"
            f"Rationale: {resolution.rationale}\n\n"
            f"Resolved text: {resolution.text}"
            for resolution in resolutions
        )
        conflict_text = "\n\n".join(conflict_sections) or "None."
        metadata = {
            "kind": "central-unit-merge-review",
            "schema": "1",
            "status": status,
            "updated": self.today.isoformat(),
        }
        body = (
            "# Central Unit Merge Review\n\n"
            "## Selected units\n"
            f"{_items(unit_ids)}\n\n"
            "## Conflicting sections\n"
            f"{conflict_text}\n\n"
            "## Accepted resolutions\n"
            f"{resolution_sections or 'None yet.'}\n\n"
            "## Preserved human edits and conflicts\n"
            f"{preserved}\n\n"
            "## Human notes\n"
            f"{previous_notes}\n"
        )
        document = _document(metadata, body)
        document = _replace_frontmatter(
            document,
            {
                _merge_review_hash_key(heading): _content_hash(
                    _section_value(document, heading)
                )
                for heading in (
                    "Selected units",
                    "Conflicting sections",
                    "Accepted resolutions",
                )
            },
        )
        self.merge_review_path.write_text(
            document.rstrip() + "\n", encoding="utf-8"
        )

    def _read_claims(self, unit_id: str) -> tuple[ClaimBlock, ...]:
        latest = _section_value(
            self._unit_path(unit_id).read_text(encoding="utf-8"), "Latest result"
        )
        claims: list[ClaimBlock] = []
        for match in re.finditer(
            r"^### Claim \d+\n(.*?)(?=^### Claim \d+\n|\Z)",
            latest,
            flags=re.MULTILINE | re.DOTALL,
        ):
            block = match.group(1)
            text_match = re.search(r"^Text:\n(.*)\Z", block, flags=re.MULTILINE | re.DOTALL)
            if not text_match:
                raise ValueError(f"Stored claim in unit {unit_id} is malformed.")
            evidence = _field(block, "Evidence IDs")
            claim = ClaimBlock(
                section=_field(block, "Section"),
                claim_level=_field(block, "Claim level"),
                contribution_type=_field(block, "Contribution type"),
                text=text_match.group(1).strip(),
                evidence_ids=tuple(item.strip() for item in evidence.split(",") if item.strip()),
                comparability_status=_field(block, "Comparability status") or "NOT_APPLICABLE",
                comparability_basis=_field(block, "Comparability basis"),
            )
            claim = _normalize_claim(claim)
            _validate_claim(claim, available_evidence=self._available_evidence_records())
            claims.append(claim)
        return tuple(claims)

    def _available_evidence_ids(self) -> set[str]:
        return set(self._available_evidence_records())

    def _available_evidence_records(self) -> dict[str, str]:
        literature_path = self.project_root / "literature-set.md"
        if not literature_path.exists():
            raise FileNotFoundError("Unit claims require the saved Research literature-set.md.")
        literature = literature_path.read_text(encoding="utf-8")
        available: dict[str, str] = {}
        registry = self._registry_readiness()
        for heading in ("Anchor/core", "Extension", "Background/definition", "Controversy"):
            for line in _section_value(literature, heading).splitlines():
                if not line.startswith("- "):
                    continue
                entry = line[2:].strip()
                identifier, separator, details = entry.partition(": ")
                if not separator:
                    identifier, separator, details = entry.partition(":")
                identifier = identifier.strip()
                if not identifier:
                    continue
                identity_match = re.search(
                    r"\[evidence-id:\s*([^;\]]+)", details, flags=re.IGNORECASE
                )
                evidence_id = identity_match.group(1).strip() if identity_match else identifier
                readiness_match = re.search(
                    r"\breadiness:\s*([A-Z_]+)", details, flags=re.IGNORECASE
                )
                readiness = (
                    readiness_match.group(1).upper()
                    if readiness_match
                    else registry.get(_canonical_evidence_id(evidence_id), "DISCOVERY_READY")
                )
                for value in (identifier, evidence_id):
                    available[value] = readiness
                    available[_canonical_evidence_id(value)] = readiness
        return available

    def _registry_readiness(self) -> dict[str, str]:
        path = self.project_root / "source-registry.md"
        if not path.exists():
            return {}
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {}
        result: dict[str, str] = {}
        header = next((line for line in lines if line.startswith("| Source ID |")), "")
        if not header:
            return result
        columns = [part.strip() for part in header.strip("|").split("|")]
        # Pre-readiness registries only described route observations and cannot
        # prove locator-bearing full text. An explicit Readiness column may
        # strengthen or preserve the fail-closed literature-set projection.
        try:
            identity_index = columns.index("Identity")
            readiness_index = columns.index("Readiness")
        except ValueError:
            return result
        for line in lines:
            if not line.startswith("|") or line == header or set(line.replace("|", "").strip()) <= {"-"}:
                continue
            values = [part.strip() for part in line.strip("|").split("|")]
            if len(values) <= max(identity_index, readiness_index):
                continue
            identity = values[identity_index]
            status = values[readiness_index].upper()
            if status not in {"DISCOVERY_READY", "EVIDENCE_READY", "CLAIM_READY"}:
                continue
            result[_canonical_evidence_id(identity)] = status
        return result

    def _content_has_merge_key(self, merge_key: str) -> bool:
        if not self.content_path.exists():
            return False
        content = self.content_path.read_text(encoding="utf-8")
        return f"Merge key: {merge_key}" in _section_value(content, "Merge history")

    def _best_preclaim_readiness(
        self, blocks: Sequence[tuple[tuple[str, ...], ClaimBlock]]
    ) -> str:
        records = self._available_evidence_records()
        evidence_ids = {
            evidence_id
            for _, claim in blocks
            for evidence_id in claim.evidence_ids
        }
        if evidence_ids and all(
            records.get(evidence_id, records.get(_canonical_evidence_id(evidence_id)))
            in {"EVIDENCE_READY", "CLAIM_READY"}
            for evidence_id in evidence_ids
        ):
            return "EVIDENCE_READY"
        return self._current_readiness()

    def _recorded_merged_unit_ids(self) -> set[str]:
        if not self.content_path.exists():
            return set()
        content = self.content_path.read_text(encoding="utf-8")
        metadata, _ = _split_frontmatter(content)
        history = _section_value(content, "Merge history")
        expected_hash = metadata.get("generated_merge_history_sha256")
        if history.strip() and (
            not expected_hash or _content_hash(history) != expected_hash
        ):
            preserved = _section_value(content, "Preserved human edits and conflicts")
            conflict = (
                "### Direct human edit detected in Merge history\n\n"
                "Recovery stopped because edited merge records cannot prove which unit content "
                "was centrally merged:\n\n"
                f"```md\n{history.rstrip()}\n```"
            )
            if conflict not in preserved:
                preserved = (preserved.rstrip() + "\n\n" + conflict).strip()
                content = _set_section(content, "Preserved human edits and conflicts", preserved)
                content = _replace_frontmatter(
                    content,
                    {
                        "merge_history_status": "HUMAN_EDIT_CONFLICT",
                        "updated": self.today.isoformat(),
                    },
                )
                self.content_path.write_text(content.rstrip() + "\n", encoding="utf-8")
            raise MergeHistoryEditConflict(
                "review-content.md Merge history was directly edited; resolve it before recovery."
            )
        recorded: set[str] = set()
        for value in re.findall(r"^Accepted units:\s*(.+)$", history, flags=re.MULTILINE):
            recorded.update(item.strip() for item in value.split(",") if item.strip())
        return recorded

    def _current_content_revision(self) -> int | None:
        if not self.content_path.exists():
            return None
        metadata, _ = _split_frontmatter(self.content_path.read_text(encoding="utf-8"))
        return int(metadata.get("content_revision", "0"))

    def _current_readiness(self) -> str:
        if not self.content_path.exists():
            return "DISCOVERY_READY"
        metadata, _ = _split_frontmatter(self.content_path.read_text(encoding="utf-8"))
        return metadata.get("readiness", "DISCOVERY_READY")

    def _content_digest(self) -> str:
        if not self.content_path.exists():
            return ""
        return _content_hash(self.content_path.read_text(encoding="utf-8"))

    def _require_plan(self) -> None:
        if not self.plan_path.exists() or not self.unit_dir.exists():
            raise FileNotFoundError("No saved research/writing unit plan.")

    def _plan_unit_ids(self) -> tuple[str, ...]:
        plan = self.plan_path.read_text(encoding="utf-8")
        return tuple(
            re.findall(r"^- ([a-z0-9][a-z0-9-]*) \(", _section_value(plan, "Units"), re.MULTILINE)
        )

    def _statuses(self) -> dict[str, str]:
        return {unit_id: self._unit_status(unit_id) for unit_id in self._plan_unit_ids()}

    def _unit_status(self, unit_id: str) -> str:
        path = self._unit_path(unit_id)
        if not path.exists():
            raise ValueError(f"Unit plan references missing asset: {unit_id}")
        metadata, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
        status = metadata.get("status", "")
        if status not in UNIT_STATUSES:
            raise ValueError(f"Unit {unit_id} has unknown status: {status}")
        return status

    def _unit_prerequisites(self, unit_id: str) -> tuple[str, ...]:
        metadata, _ = _split_frontmatter(
            self._unit_path(unit_id).read_text(encoding="utf-8")
        )
        value = metadata.get("prerequisites", "NONE")
        if value == "NONE":
            return ()
        return tuple(item.strip() for item in value.split(",") if item.strip())

    def _update_unit_metadata(self, unit_id: str, updates: Mapping[str, str]) -> None:
        path = self._unit_path(unit_id)
        text = _replace_frontmatter(path.read_text(encoding="utf-8"), updates)
        path.write_text(text.rstrip() + "\n", encoding="utf-8")

    def _unit_path(self, unit_id: str) -> Path:
        if not UNIT_ID_PATTERN.fullmatch(unit_id):
            raise ValueError("Unit IDs use lowercase letters, digits, and hyphens only.")
        return self.unit_dir / f"{unit_id}.md"


def _validate_claim(
    claim: ClaimBlock,
    *,
    available_evidence: set[str] | Mapping[str, str],
) -> None:
    if claim.claim_level not in CLAIM_LEVELS:
        raise ValueError("Unknown claim level: " + claim.claim_level)
    if claim.contribution_type not in CONTRIBUTION_TYPES:
        raise ValueError("Unknown contribution type: " + claim.contribution_type)
    if claim.comparability_status not in COMPARABILITY_STATUSES:
        raise ValueError("Unknown comparability status: " + claim.comparability_status)
    if not claim.section.strip() or "\n" in claim.section or not claim.text.strip():
        raise ValueError("Claim blocks require a one-line section and non-empty text.")
    evidence_ids = _nonblank(claim.evidence_ids)
    if claim.claim_level == "SOURCE_FACT" and not evidence_ids:
        raise ValueError("SOURCE_FACT claim blocks require evidence IDs.")
    records = (
        {value: "EVIDENCE_READY" for value in available_evidence}
        if not isinstance(available_evidence, Mapping)
        else dict(available_evidence)
    )
    matched: dict[str, str] = {}
    missing: set[str] = set()
    for evidence_id in evidence_ids:
        canonical = _canonical_evidence_id(evidence_id)
        if evidence_id in records:
            matched[evidence_id] = records[evidence_id]
        elif canonical in records:
            matched[evidence_id] = records[canonical]
        else:
            missing.add(evidence_id)
    if missing:
        raise ValueError(
            "Claim evidence IDs are absent from Research literature-set.md: "
            + ", ".join(sorted(missing))
        )
    if claim.claim_level == "SOURCE_FACT":
        not_ready = {
            evidence_id: readiness
            for evidence_id, readiness in matched.items()
            if readiness not in {"EVIDENCE_READY", "CLAIM_READY"}
        }
        if not_ready:
            details = ", ".join(
                f"{evidence_id} ({readiness})"
                for evidence_id, readiness in sorted(not_ready.items())
            )
            raise ValueError(
                "SOURCE_FACT claims require EVIDENCE_READY evidence; "
                "metadata-only records remain discovery-only: " + details
            )


def _claim_is_ready(claim: ClaimBlock) -> bool:
    """Require an explicit chemistry-comparability decision for cross-study claims."""

    cross_study = len(_nonblank(claim.evidence_ids)) > 1 and claim.contribution_type in {
        "comparison",
        "explanation",
        "rebuttal",
        "trend",
        "hypothesis",
    }
    if not cross_study:
        return True
    return (
        claim.comparability_status == "COMPARABLE"
        and bool(claim.comparability_basis.strip())
    )


def _normalize_claim(claim: ClaimBlock) -> ClaimBlock:
    return replace(
        claim,
        evidence_ids=tuple(_canonical_evidence_id(item) for item in _nonblank(claim.evidence_ids)),
    )


def _canonical_evidence_id(value: str) -> str:
    try:
        from research import canonical_evidence_id

        return canonical_evidence_id(value)
    except (ImportError, ValueError):
        return value.strip()


def _render_result(result: UnitResult) -> str:
    claims = "\n\n".join(
        f"### Claim {index}\n"
        f"Section: {claim.section.strip()}\n"
        f"Claim level: {claim.claim_level}\n"
        f"Contribution type: {claim.contribution_type}\n"
        f"Evidence IDs: {', '.join(_nonblank(claim.evidence_ids)) or 'NONE'}\n"
        f"Comparability status: {claim.comparability_status}\n"
        f"Comparability basis: {claim.comparability_basis.strip() or 'Not recorded.'}\n"
        f"Text:\n{claim.text.strip()}"
        for index, claim in enumerate(result.claims, start=1)
    )
    return (
        f"Completion evidence: {result.completion_evidence.strip() or 'Not completed.'}\n\n"
        "Findings:\n"
        f"{_items(result.findings)}\n\n"
        f"Remaining uncertainty: {result.remaining_uncertainty.strip()}\n\n"
        f"Tool degradation: {result.tool_degradation.strip() or 'None.'}\n\n"
        f"HUMAN_ACTION_REQUIRED: {result.human_action_required.strip() or 'None.'}\n\n"
        f"{claims or 'No claim blocks proposed.'}"
    )


def _render_content_blocks(
    revision: int, blocks: Sequence[tuple[tuple[str, ...], ClaimBlock]]
) -> str:
    return "\n\n".join(
        f"### Merge {revision} · Block {index}\n"
        f"Section: {claim.section.strip()}\n"
        f"Claim level: {claim.claim_level}\n"
        f"Contribution type: {claim.contribution_type}\n"
        f"Source units: {', '.join(source_units)}\n"
        f"Evidence IDs: {', '.join(_nonblank(claim.evidence_ids)) or 'NONE'}\n"
        f"Comparability status: {claim.comparability_status}\n"
        f"Comparability basis: {claim.comparability_basis.strip() or 'Not recorded.'}\n"
        f"Text:\n{claim.text.strip()}"
        for index, (source_units, claim) in enumerate(blocks, start=1)
    ) or "No content blocks added in this merge."


def _field(block: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.*)$", block, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _items(values: Sequence[str]) -> str:
    return "\n".join(f"- {value.strip()}" for value in values if value.strip()) or "- None recorded."


def _nonblank(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(value.strip() for value in values if value.strip())


def _content_hash(value: str) -> str:
    normalized = value.strip().replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _merge_key(
    unit_ids: tuple[str, ...],
    blocks: Sequence[tuple[tuple[str, ...], ClaimBlock]],
) -> str:
    lines = ["units=" + ",".join(unit_ids)]
    for source_units, claim in blocks:
        lines.extend(
            (
                "source_units=" + ",".join(source_units),
                "section=" + claim.section.strip(),
                "claim_level=" + claim.claim_level,
                "contribution_type=" + claim.contribution_type,
                "evidence_ids=" + ",".join(_nonblank(claim.evidence_ids)),
                "comparability_status=" + claim.comparability_status,
                "comparability_basis=" + claim.comparability_basis.strip(),
                "text=" + claim.text.strip(),
            )
        )
    return _content_hash("\n".join(lines))


def _merge_review_hash_key(heading: str) -> str:
    normalized = heading.lower().replace(" ", "_")
    return f"generated_{normalized}_sha256"
