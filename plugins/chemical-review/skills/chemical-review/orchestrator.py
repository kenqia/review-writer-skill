"""Small, file-backed orchestrator for the chemical-review skill.

The orchestrator owns phase transitions and the central merge boundary while
stage modules own their human-readable Markdown assets. Keeping this seam
executable makes start/resume, confirmation, dependency, and write-ownership
boundaries testable without introducing a service or a second state store.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
import re
import shutil
from typing import Mapping, Sequence


PHASES = ("GRILL", "RESEARCH", "PROTOTYPE", "PRD", "ISSUES", "IMPLEMENT", "REVIEW")
STATUSES = ("ACTIVE", "WAITING_FOR_HUMAN", "READY_FOR_NEXT_PHASE", "CANDIDATE_READY")
EXECUTION_MODES = ("continuous", "acceptance")

_INTENT_HEADINGS = {
    "research_question": "Research question",
    "core_claim_candidates": "Core-claim candidates",
    "scope": "Scope and exclusions",
    "audience": "Audience or target journal",
    "target_journal": "Audience or target journal",
    "expected_contribution": "Expected contribution",
    "known_facts": "Known facts",
    "researcher_context": "Researcher context and prior knowledge",
    "evidence_standards": "Evidence standards and constraints",
    "frontier_interview": "Frontier interview",
}
_DOMAIN_HEADINGS = {
    "chemical_subfield": "Chemical subfield",
    "core_systems": "Core systems",
    "terms": "Canonical terms and synonyms",
    "boundary_scenarios": "Boundary scenarios",
    "evidence_expectations": "Evidence expectations",
    "known_capability_limits": "Known capability limits",
}
_ALIASES = {
    "question": "research_question",
    "research_question": "research_question",
    "core_claim": "core_claim_candidates",
    "core_claims": "core_claim_candidates",
    "core_claim_candidates": "core_claim_candidates",
    "scope": "scope",
    "scope_and_exclusions": "scope",
    "exclusions": "exclusions",
    "audience": "audience",
    "audience_or_target_journal": "audience",
    "target_reader": "audience",
    "target_journal": "target_journal",
    "journal": "target_journal",
    "journal_guide_locator": "journal_guide_locator",
    "official_guide_locator": "journal_guide_locator",
    "contribution": "expected_contribution",
    "expected_contribution": "expected_contribution",
    "chemical_subfield": "chemical_subfield",
    "core_systems": "core_systems",
    "terms": "terms",
    "canonical_terms": "terms",
    "boundary_scenarios": "boundary_scenarios",
    "evidence_expectations": "evidence_expectations",
    "known_capability_limits": "known_capability_limits",
    "known_facts": "known_facts",
    "researcher_context": "researcher_context",
    "background": "researcher_context",
    "prior_knowledge": "researcher_context",
    "evidence_standard": "evidence_standards",
    "evidence_standards": "evidence_standards",
    "evidence_expectation": "evidence_expectations",
    "constraints": "evidence_standards",
    "controversies": "frontier_interview",
    "research_preferences": "frontier_interview",
}


@dataclass(frozen=True)
class WorkflowResult:
    """The user-visible projection returned by one orchestrator invocation."""

    phase: str
    status: str
    next_action: str
    intent_confirmation: str
    human_action: str
    intent_revision: int
    assets: Mapping[str, str]
    execution_mode: str = "acceptance"
    frontier_questions: tuple[str, ...] = ()
    known_facts: tuple[str, ...] = ()

    @property
    def mode(self) -> str:
        """Short compatibility spelling for user-facing callers."""

        return self.execution_mode


class ChemicalReviewOrchestrator:
    """Persist and resume the lightweight chemical-review workflow."""

    def __init__(self, project_root: str | Path, *, today: date | None = None) -> None:
        self.project_root = Path(project_root)
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.today = today or date.today()

    @property
    def state_path(self) -> Path:
        return self.project_root / "workflow-state.md"

    @property
    def intent_path(self) -> Path:
        return self.project_root / "review-intent.md"

    @property
    def domain_path(self) -> Path:
        return self.project_root / "domain-profile.md"

    def start(
        self,
        topic: str,
        *,
        mode: str | None = None,
        execution_mode: str | None = None,
        materials: Mapping[str, str | Path] | Sequence[str | Path] | None = None,
        known_documents: Mapping[str, str | Path] | Sequence[str | Path] | None = None,
    ) -> WorkflowResult:
        """Start from a topic, or resume if this project already has state."""

        if mode is not None and execution_mode is not None and mode != execution_mode:
            raise ValueError("mode and execution_mode must agree when both are provided.")
        selected_mode = self._normalize_execution_mode(
            execution_mode if execution_mode is not None else mode
        )

        supplied_materials = materials if materials is not None else known_documents
        if self.state_path.exists():
            if selected_mode is not None:
                current = self._require_state().get("execution_mode", "acceptance")
                if current != selected_mode:
                    raise ValueError(
                        "The project execution mode is already persisted as " + current
                    )
            if supplied_materials:
                self._ingest_known_materials(supplied_materials)
            return self.resume()
        topic = topic.strip()
        if not topic:
            raise ValueError("A chemistry review topic or research idea is required.")

        self._write_initial_assets(
            topic,
            execution_mode=selected_mode or "acceptance",
            materials=supplied_materials,
        )
        return self.resume()

    def resume(self) -> WorkflowResult:
        """Reload the Markdown state after a cold restart."""

        if not self.state_path.exists():
            raise FileNotFoundError(f"No workflow state at {self.state_path}")
        for path in (self.intent_path, self.domain_path):
            if not path.exists():
                raise FileNotFoundError(f"Workflow state exists but asset is missing: {path}")
        metadata, _ = _split_frontmatter(self.state_path.read_text(encoding="utf-8"))
        intent_metadata, _ = _split_frontmatter(self.intent_path.read_text(encoding="utf-8"))
        domain_metadata, _ = _split_frontmatter(self.domain_path.read_text(encoding="utf-8"))
        if intent_metadata.get("kind") != "review-intent":
            raise ValueError("review-intent.md has the wrong asset kind")
        if domain_metadata.get("kind") != "domain-profile":
            raise ValueError("domain-profile.md has the wrong asset kind")
        missing = {key for key in ("phase", "status", "next_action") if not metadata.get(key)}
        if missing:
            raise ValueError(f"Malformed workflow state; missing: {', '.join(sorted(missing))}")
        phase = metadata["phase"]
        status = metadata["status"]
        if phase not in PHASES:
            raise ValueError(f"Unknown workflow phase: {phase}")
        if status not in STATUSES:
            raise ValueError(f"Unknown workflow status: {status}")
        return WorkflowResult(
            phase=phase,
            status=status,
            next_action=metadata["next_action"],
            intent_confirmation=metadata.get("intent_confirmation", "NOT_REQUIRED"),
            human_action=metadata.get("human_action", "NONE"),
            intent_revision=int(metadata.get("intent_revision", "0")),
            assets=metadata,
            execution_mode=metadata.get("execution_mode", "acceptance"),
            frontier_questions=tuple(self._frontier_questions_from_assets()),
            known_facts=tuple(self._known_facts_from_intent()),
        )

    def continue_grill(self, answers: Mapping[str, str]) -> WorkflowResult:
        """Apply ordinary-language Grill answers without guessing omissions."""

        self._require_state("GRILL")
        intent = self.intent_path.read_text(encoding="utf-8")
        domain = self.domain_path.read_text(encoding="utf-8")
        normalized = self._normalize_answers(answers)
        intent = self._apply_intent_answers(intent, normalized)
        intent = self._apply_journal_answers(intent, normalized)
        domain = self._apply_domain_answers(domain, normalized)
        missing = self._missing_intent_fields(intent)
        open_questions = "None recorded." if not missing else "\n".join(f"- {item}" for item in missing)
        intent = _set_section(intent, "Open questions", open_questions)
        self._write(self.intent_path, intent)
        self._write(self.domain_path, domain)

        journal_unresolved = _is_open(_section_value(intent, "Audience or target journal"))
        if not journal_unresolved:
            selected_journal = _target_journal_from_intent(intent)
            intent = _replace_frontmatter(
                intent,
                {
                    "journal_status": "SELECTED" if selected_journal else "NOT_REQUIRED",
                    "journal_confirmation": "CONFIRMED" if selected_journal else "NOT_APPLICABLE",
                },
            )
            self._write(self.intent_path, intent)
        if missing:
            self._update_state(
                status="ACTIVE",
                next_action="continue Grill by answering the open questions in review-intent.md.",
                intent_confirmation="REQUIRED",
                human_action="NONE",
                open_questions=open_questions,
                resume_note="The project remains in Grill until the core intent is clear.",
            )
        elif journal_unresolved:
            self._update_state(
                status="WAITING_FOR_HUMAN",
                next_action=(
                    "Provide a target reader, select a target journal, or ask the agent to propose "
                    "a small set of journal candidates before Research."
                ),
                intent_confirmation="REQUIRED",
                journal_status="UNSET",
                journal_confirmation="REQUIRED",
                human_action="REQUIRED",
                open_questions="Target reader or journal selection is still required.",
                resume_note="The core chemistry intent is drafted, but the reader/journal boundary is unresolved.",
            )
        else:
            self._update_state(
                status="READY_FOR_NEXT_PHASE",
                next_action="Confirm the Grill contract before starting Research.",
                intent_confirmation="REQUIRED",
                journal_status=(
                    "SELECTED"
                    if _target_journal_from_intent(intent)
                    else "NOT_REQUIRED"
                ),
                journal_confirmation=(
                    "CONFIRMED"
                    if _target_journal_from_intent(intent)
                    else "NOT_APPLICABLE"
                ),
                human_action="NONE",
                open_questions="None recorded.",
                resume_note="All required Grill fields are present; human confirmation is still required.",
            )
        return self.resume()

    def confirm_current_intent(self) -> WorkflowResult:
        """Confirm the current Grill contract and hand off to Research."""

        state = self._require_state("GRILL")
        if state.get("status") != "READY_FOR_NEXT_PHASE":
            raise ValueError("The Grill contract is incomplete; answer its open questions first.")
        if state.get("journal_status") == "SELECTED" and state.get("journal_guide_status") != "FETCHED":
            raise ValueError(
                "The selected journal's current official guide must be fetched before Research."
            )
        intent = self.intent_path.read_text(encoding="utf-8")
        intent = _replace_frontmatter(intent, {"confirmation": "CONFIRMED"})
        self._write(self.intent_path, intent)
        self._update_state(
            phase="RESEARCH",
            status="ACTIVE",
            next_action="Build the research evidence packet from the confirmed intent.",
            intent_confirmation="CONFIRMED",
            journal_confirmation=state.get("journal_confirmation", "NOT_APPLICABLE"),
            human_action="NONE",
            resume_note="Research is the first downstream phase after the confirmed Grill contract.",
        )
        return self.resume()

    def propose_journal_candidates(self, candidates) -> WorkflowResult:
        """Persist a small set of journal options for explicit researcher choice."""

        from review import JournalCandidate

        self._require_state("GRILL")
        values = tuple(candidates)
        if not 1 <= len(values) <= 3 or not all(
            isinstance(candidate, JournalCandidate) for candidate in values
        ):
            raise ValueError("Journal candidate proposals must contain one to three JournalCandidate values.")
        names = [candidate.target_journal.strip() for candidate in values]
        if len(set(names)) != len(names) or any(
            not candidate.target_journal.strip()
            or not candidate.rationale.strip()
            or not candidate.official_guide_locator.strip()
            for candidate in values
        ):
            raise ValueError("Journal candidates require unique names, rationales, and official guide locators.")
        intent = self.intent_path.read_text(encoding="utf-8")
        rendered = "\n".join(
            f"- Journal: {candidate.target_journal.strip()}\n"
            f"  Rationale: {candidate.rationale.strip()}\n"
            f"  Official guide: {candidate.official_guide_locator.strip()}"
            for candidate in values
        )
        intent = _set_section(intent, "Journal candidates", rendered)
        intent = _replace_frontmatter(
            intent,
            {
                "journal_status": "PROPOSED",
                "journal_confirmation": "REQUIRED",
            },
        )
        self._write(self.intent_path, intent)
        self._update_state(
            status="WAITING_FOR_HUMAN",
            next_action="Confirm one proposed target journal before fetching its current official guide.",
            intent_confirmation="REQUIRED",
            journal_status="PROPOSED",
            journal_confirmation="REQUIRED",
            human_action="REQUIRED",
            open_questions="Choose one proposed target journal.",
            resume_note="Journal candidates are suggestions only; no target journal has been silently selected.",
        )
        return self.resume()

    def confirm_journal_candidate(self, target_journal: str) -> WorkflowResult:
        """Confirm one proposed target journal without fetching it implicitly."""

        state = self._require_state("GRILL")
        if state.get("journal_status") != "PROPOSED":
            raise ValueError("There are no pending journal candidates to confirm.")
        intent = self.intent_path.read_text(encoding="utf-8")
        candidates = _parse_journal_candidates(_section_value(intent, "Journal candidates"))
        selected = next(
            (candidate for candidate in candidates if candidate.target_journal == target_journal.strip()),
            None,
        )
        if selected is None:
            raise ValueError("The selected journal is not one of the proposed candidates.")
        intent = _set_section(
            intent,
            "Audience or target journal",
            f"Target journal: {selected.target_journal}\n"
            f"Official guide: {selected.official_guide_locator}\n"
            f"Selection rationale: {selected.rationale}",
        )
        intent = _replace_frontmatter(
            intent,
            {
                "journal_status": "SELECTED",
                "journal_confirmation": "CONFIRMED",
                "target_journal": selected.target_journal,
                "journal_guide_locator": selected.official_guide_locator,
            },
        )
        self._write(self.intent_path, intent)
        missing = self._missing_intent_fields(intent)
        self._update_state(
            status="ACTIVE" if missing else "READY_FOR_NEXT_PHASE",
            next_action=(
                "Continue Grill by answering the remaining open questions."
                if missing
                else "Fetch the selected journal's current official guide, then confirm the Grill contract."
            ),
            intent_confirmation="REQUIRED",
            journal_status="SELECTED",
            journal_confirmation="CONFIRMED",
            human_action="NONE",
            open_questions=("\n".join(f"- {item}" for item in missing) if missing else "None recorded."),
            resume_note="The researcher selected the target journal; its current official guide is still a required input.",
        )
        return self.resume()

    def fetch_selected_journal_guide(self, *, fetcher=None) -> WorkflowResult:
        """Read and persist the selected journal's current official author guide."""

        from review import HttpJournalGuideFetcher, JournalCandidate

        state = self._require_state()
        if state.get("journal_status") != "SELECTED":
            raise ValueError("Select a target journal before fetching its official guide.")
        intent_metadata, _ = _split_frontmatter(self.intent_path.read_text(encoding="utf-8"))
        target_journal = intent_metadata.get("target_journal", "").strip()
        locator = intent_metadata.get("journal_guide_locator", "").strip()
        if not target_journal or not locator:
            raise ValueError("The selected journal must retain its official guide locator.")
        candidate = JournalCandidate(target_journal, "Confirmed target journal", locator)
        try:
            snapshot = (fetcher or HttpJournalGuideFetcher()).fetch(candidate)
        except Exception:
            self._update_state(
                status="WAITING_FOR_HUMAN",
                next_action=(
                    "HUMAN_ACTION_REQUIRED: restore access to the official journal guide or provide "
                    "a fresh official guide locator, then retry."
                ),
                journal_guide_status=state.get("journal_guide_status", "NONE"),
                human_action="REQUIRED",
                open_questions="The selected journal guide could not be fetched.",
                resume_note=(
                    "No replacement guide was persisted; any existing journal-profile.md remains authoritative "
                    "until a refreshed guide is captured."
                ),
            )
            return self.resume()
        guide = _document(
            {
                "kind": "journal-guide-snapshot",
                "schema": "1",
                "target_journal": snapshot.target_journal,
                "source_locator": snapshot.source_locator,
                "retrieved_at": snapshot.retrieved_at,
                "content_digest": snapshot.content_digest,
                "updated": self.today.isoformat(),
            },
            "# Official Journal Guide Snapshot\n\n"
            f"## Target journal\n{snapshot.target_journal}\n\n"
            f"## Source locator\n{snapshot.source_locator}\n\n"
            f"## Guide content\n{snapshot.content}\n",
        )
        self._write(self.project_root / "journal-guide.md", guide)
        from delivery import JournalProfile

        profile = JournalProfile.from_guide_snapshot(self.project_root)
        profile.persist(self.project_root)
        self._update_state(
            journal_guide_status="FETCHED",
            journal_guide_locator=snapshot.source_locator,
            journal_guide_digest=snapshot.content_digest,
            next_action="Review the fetched official guide, then confirm the Grill contract before Research.",
            human_action="NONE",
            resume_note="The current official journal guide is saved with locator and content digest.",
        )
        return self.resume()

    def run_research(self, config=None) -> WorkflowResult:
        """Run or rerun Research with replaceable adapters and persist its assets."""

        from research import ResearchConfig, ResearchRunner

        self._require_state("RESEARCH")
        if config is None:
            state = self._require_state("RESEARCH")
            config = ResearchConfig.default()
            saved_dir = state.get("authorized_pdf_dir", "").strip()
            saved_paths = tuple(
                item.strip()
                for item in state.get("authorized_pdf_paths", "").splitlines()
                if item.strip() and item.strip() != "NONE"
            )
            if saved_dir and saved_dir != "NONE":
                config = replace(config, authorized_pdf_dir=saved_dir)
            if saved_paths:
                config = replace(config, user_pdfs=saved_paths)
        if not isinstance(config, ResearchConfig):
            raise TypeError("config must be a ResearchConfig")
        result = ResearchRunner(self.project_root, today=self.today).run(
            self.intent_path.read_text(encoding="utf-8"),
            self.domain_path.read_text(encoding="utf-8"),
            config,
            intent_revision=self.resume().assets.get("intent_revision", "0"),
        )
        self._update_state(
            status=result.status,
            next_action=result.next_action,
            human_action=result.human_action,
            research_handoff=result.handoff or "NONE",
            research_handoff_rationale=result.handoff_rationale,
            readiness=result.assets.get("readiness", getattr(result, "readiness", "DISCOVERY_READY")),
            readiness_reason=result.assets.get("readiness_reason", "Readiness is recorded in research-evidence.md."),
            readiness_missing=result.assets.get("readiness_missing", "None recorded."),
            coverage=result.assets.get("coverage", "None recorded."),
            stopping_reason=result.assets.get("stopping_reason", "None recorded."),
            source_registry=result.assets.get("source_registry", "source-registry.md"),
            run_budget=result.assets.get("run_budget", "run-budget.json"),
            authorized_pdf_dir=result.assets.get("authorized_pdf_dir", "NONE"),
            authorized_pdf_paths=result.assets.get("authorized_pdf_paths", "NONE"),
            cloud_parser_consent=result.assets.get("cloud_parser_consent", "NOT_GRANTED"),
            cloud_parser_consent_asset=result.assets.get(
                "cloud_parser_consent_asset", "NONE"
            ),
            tool_degradation=result.assets.get("tool_degradation", "None recorded."),
            resume_note="Research assets are persisted; rerun this phase after configuring a missing capability or accepting its handoff.",
        )
        return self.resume()

    def accept_research_handoff(self) -> WorkflowResult:
        """Accept the saved Research proposal and move to Prototype or PRD."""

        state = self._require_state("RESEARCH")
        if state.get("status") != "READY_FOR_NEXT_PHASE":
            raise ValueError("Research is not ready for a handoff.")
        target = state.get("research_handoff", "NONE")
        if target not in {"PROTOTYPE", "PRD"}:
            raise ValueError("The saved Research handoff must target PROTOTYPE or PRD.")
        self._update_state(
            phase=target,
            status="ACTIVE",
            next_action=f"Start the {target} phase from the saved Research evidence package.",
            human_action="NONE",
            resume_note=f"Research handoff accepted; {target} is now the current phase.",
        )
        return self.resume()

    def run_prototype(self, submission) -> WorkflowResult:
        """Run a small-sample review Prototype from saved Research assets."""

        from prototype import PrototypeRunner, PrototypeSubmission

        self._require_state("PROTOTYPE")
        if not isinstance(submission, PrototypeSubmission):
            raise TypeError("submission must be a PrototypeSubmission")
        result = PrototypeRunner(self.project_root, today=self.today).run(submission)
        self._update_state(
            status="READY_FOR_NEXT_PHASE",
            next_action=(
                f"Review the Prototype decision and accept the {result.handoff} handoff, "
                "or rerun Prototype with a different small sample."
            ),
            prototype_value_status=result.value_status,
            prototype_handoff=result.handoff,
            prototype_handoff_rationale=result.rationale,
            human_action="NONE",
            resume_note="The Prototype result is saved and can be rerun without changing Research assets.",
        )
        return self.resume()

    def accept_prototype_handoff(self) -> WorkflowResult:
        """Accept only the Prototype handoff saved by its latest run."""

        state = self._require_state("PROTOTYPE")
        if state.get("status") != "READY_FOR_NEXT_PHASE":
            raise ValueError("Prototype has no ready handoff.")
        target = state.get("prototype_handoff", "NONE")
        if target not in {"RESEARCH", "PRD"}:
            raise ValueError("The saved Prototype handoff must target RESEARCH or PRD.")
        self._update_state(
            phase=target,
            status="ACTIVE",
            next_action=(
                "Continue adaptive Research from the Prototype risks."
                if target == "RESEARCH"
                else "Build an adaptable review blueprint from the saved intent, Research, and Prototype assets."
            ),
            human_action="NONE",
            resume_note=f"The researcher accepted the Prototype handoff to {target}.",
        )
        return self.resume()

    def build_review_blueprint(self, proposal) -> WorkflowResult:
        """Build the first adaptable PRD blueprint without freezing prose or papers."""

        from prototype import BlueprintBuilder, BlueprintProposal

        self._require_state("PRD")
        if not isinstance(proposal, BlueprintProposal):
            raise TypeError("proposal must be a BlueprintProposal")
        revision = BlueprintBuilder(self.project_root, today=self.today).build(proposal)
        self._update_state(
            status="READY_FOR_NEXT_PHASE",
            next_action="Review and accept the adaptable blueprint, or revise it when evidence changes.",
            blueprint_status="ADAPTABLE",
            blueprint_revision=str(revision),
            human_action="NONE",
            resume_note="The blueprint is saved; Research and Prototype assets remain unchanged.",
        )
        return self.resume()

    def revise_review_blueprint(
        self, changes: Mapping[str, str | tuple[str, ...]], *, evidence_note: str
    ) -> WorkflowResult:
        """Revise selected blueprint sections and preserve a reasoned history."""

        from prototype import BlueprintBuilder

        self._require_state("PRD")
        revision = BlueprintBuilder(self.project_root, today=self.today).revise(
            changes, evidence_note=evidence_note
        )
        self._update_state(
            status="READY_FOR_NEXT_PHASE",
            next_action="Review and accept blueprint revision " + str(revision) + ", or continue adapting it.",
            blueprint_status="ADAPTABLE",
            blueprint_revision=str(revision),
            human_action="NONE",
            resume_note="Only the requested blueprint sections changed; prior revisions remain visible.",
        )
        return self.resume()

    def accept_review_blueprint(self) -> WorkflowResult:
        """Accept the saved PRD blueprint and enter Issues decomposition."""

        state = self._require_state("PRD")
        if state.get("status") != "READY_FOR_NEXT_PHASE":
            raise ValueError("The review blueprint is not ready for acceptance.")
        if not (self.project_root / "review-blueprint.md").exists():
            raise FileNotFoundError("PRD acceptance requires review-blueprint.md.")
        self._update_state(
            phase="ISSUES",
            status="ACTIVE",
            next_action="Decompose the accepted blueprint into dependency-aware research/writing units.",
            human_action="NONE",
            resume_note="The adaptable blueprint remains saved while Issues defines executable units.",
        )
        return self.resume()

    def create_review_units(self, units) -> WorkflowResult:
        """Persist the Issues dependency graph without executing any unit."""

        from units import ResearchWritingUnit, UnitManager

        self._require_state("ISSUES")
        candidates = tuple(units)
        if not all(isinstance(unit, ResearchWritingUnit) for unit in candidates):
            raise TypeError("units must contain only ResearchWritingUnit values")
        ready = UnitManager(self.project_root, today=self.today).create_plan(candidates)
        self._update_state(
            status="READY_FOR_NEXT_PHASE",
            next_action="Review and accept the unit plan before Implement executes ready units.",
            unit_plan_status="READY_FOR_ACCEPTANCE",
            unit_ready=", ".join(ready) or "NONE",
            human_action="NONE",
            resume_note="Each unit has its own Markdown asset; the review content source is not created yet.",
        )
        return self.resume()

    def accept_unit_plan(self) -> WorkflowResult:
        """Accept the saved unit graph and enter Implement."""

        from units import UnitManager

        state = self._require_state("ISSUES")
        if state.get("status") != "READY_FOR_NEXT_PHASE":
            raise ValueError("The research/writing unit plan is not ready for acceptance.")
        manager = UnitManager(self.project_root, today=self.today)
        ready = manager.ready_unit_ids()
        self._update_state(
            phase="IMPLEMENT",
            status="ACTIVE",
            next_action="Execute ready units independently: " + (", ".join(ready) or "none"),
            unit_plan_status="ACCEPTED",
            unit_ready=", ".join(ready) or "NONE",
            human_action="NONE",
            resume_note="Implement can collect ready unit results in any order; only central merge writes review-content.md.",
        )
        return self.resume()

    def ready_review_units(self) -> tuple[str, ...]:
        """Return the independently executable unit IDs after a cold restart."""

        from units import UnitManager

        self._require_state("IMPLEMENT")
        return UnitManager(self.project_root, today=self.today).ready_unit_ids()

    def submit_review_unit_result(self, result) -> WorkflowResult:
        """Store one unit-local result without modifying the central content source."""

        from units import UnitManager, UnitResult

        self._require_state("IMPLEMENT")
        if not isinstance(result, UnitResult):
            raise TypeError("result must be a UnitResult")
        progress = UnitManager(self.project_root, today=self.today).submit_result(result)
        if progress.unit_status == "BLOCKED":
            status = "ACTIVE" if progress.ready_ids else "WAITING_FOR_HUMAN"
            next_action = (
                "Continue independent ready units: " + ", ".join(progress.ready_ids)
                if progress.ready_ids
                else progress.human_action_required
            )
            human_action = "REQUIRED"
        elif progress.all_results_complete:
            status = "READY_FOR_NEXT_PHASE"
            next_action = "Centrally merge completed unit results into review-content.md."
            human_action = "NONE"
        else:
            status = "ACTIVE"
            next_action = "Execute ready units independently: " + (
                ", ".join(progress.ready_ids) or "none"
            )
            human_action = "REQUIRED" if progress.blocked_ids else "NONE"
        self._update_state(
            status=status,
            next_action=next_action,
            unit_ready=", ".join(progress.ready_ids) or "NONE",
            human_action=human_action,
            tool_degradation=progress.tool_degradation or None,
            open_questions=(
                "Blocked units: " + ", ".join(progress.blocked_ids)
                if progress.blocked_ids
                else None
            ),
            resume_note="Unit results remain isolated until the orchestrator performs a visible central merge.",
        )
        return self.resume()

    def submit_ready_unit_results(self, results) -> WorkflowResult:
        """Submit one execution batch and project a resumable boundary.

        Continuous projects centrally merge the completed batch once. Acceptance
        projects deliberately stop after the batch so the stage boundary stays
        visible. Already complete/merged units are skipped on resume, making a
        retried batch idempotent at the user-facing seam.
        """

        from units import UnitManager, UnitResult

        self._require_state("IMPLEMENT")
        batch = tuple(results)
        if not batch:
            raise ValueError("A ready-unit batch requires at least one UnitResult.")
        if not all(isinstance(result, UnitResult) for result in batch):
            raise TypeError("results must contain only UnitResult values")
        manager = UnitManager(self.project_root, today=self.today)
        processed = False
        latest_progress = None
        for result in batch:
            status = manager.unit_status(result.unit_id)
            if status in {"COMPLETE", "MERGED"}:
                continue
            if status != "READY":
                raise ValueError(
                    f"Unit {result.unit_id} is not ready; complete its prerequisites first."
                )
            latest_progress = manager.submit_result(result)
            processed = True
        if not processed:
            return self.resume()

        all_unit_ids = manager.unit_ids()
        blocked_ids = tuple(
            unit_id for unit_id in all_unit_ids if manager.unit_status(unit_id) == "BLOCKED"
        )
        ready_ids = manager.ready_unit_ids()
        all_results_complete = all(
            manager.unit_status(unit_id) in {"COMPLETE", "MERGED"}
            for unit_id in all_unit_ids
        )
        if blocked_ids:
            reason = latest_progress.human_action_required if latest_progress else "Resolve the blocked unit."
            next_action = "HUMAN_ACTION_REQUIRED: " + reason
            if ready_ids:
                next_action += " Continue independent ready units: " + ", ".join(ready_ids)
            status = "ACTIVE" if ready_ids else "WAITING_FOR_HUMAN"
            self._update_state(
                status=status,
                next_action=next_action,
                unit_ready=", ".join(ready_ids) or "NONE",
                human_action="REQUIRED",
                open_questions="Blocked units: " + ", ".join(blocked_ids),
                resume_note="A hard unit blocker is persisted; resolve the human action, retry, and resume this batch.",
            )
            return self.resume()
        if all_results_complete and self._execution_mode() == "continuous":
            return self.merge_review_units(manager.completed_unit_ids())

        next_action = (
            "Acceptance checkpoint: centrally merge completed unit results into review-content.md."
            if all_results_complete
            else "Execute ready units independently: " + (", ".join(ready_ids) or "none")
        )
        self._update_state(
            status="READY_FOR_NEXT_PHASE" if all_results_complete else "ACTIVE",
            next_action=next_action,
            unit_ready=", ".join(ready_ids) or "NONE",
            human_action="NONE",
            open_questions="None recorded.",
            resume_note=(
                "Acceptance mode preserves the stage boundary; completed unit results remain isolated until central merge."
                if all_results_complete
                else "The execution batch completed; ready dependencies are persisted for the next batch."
            ),
        )
        return self.resume()

    def run_continuous(self, results) -> WorkflowResult:
        """Execute a continuous-mode ready-unit batch through the public seam."""

        if self._execution_mode() != "continuous":
            raise ValueError("run_continuous requires a project persisted with continuous mode.")
        return self.submit_ready_unit_results(results)

    execute_continuous = run_continuous

    def run_continuous_cycle(
        self,
        *,
        research_config=None,
        prototype_submission=None,
        blueprint_proposal=None,
        units=(),
        unit_results=(),
        review_assessment=None,
        journal_adaptation=None,
    ) -> WorkflowResult:
        """Advance every supplied, non-blocked phase in one continuous cycle.

        Continuous mode removes ordinary acceptance prompts, but it cannot
        invent a missing scientific input.  Optional phase payloads are used
        once when their phase is active; a missing payload returns the saved
        state and its actionable ``next_action``.  Hard blockers and human
        review remain visible and resumable.
        """

        if self._execution_mode() != "continuous":
            raise ValueError("run_continuous_cycle requires a continuous project.")
        if research_config is not None:
            from research import ResearchConfig

            if not isinstance(research_config, ResearchConfig):
                raise TypeError("research_config must be a ResearchConfig")
        from prototype import BlueprintProposal, PrototypeSubmission
        from review import ReviewAssessment
        from units import ResearchWritingUnit, UnitResult

        if prototype_submission is not None and not isinstance(
            prototype_submission, PrototypeSubmission
        ):
            raise TypeError("prototype_submission must be a PrototypeSubmission")
        if blueprint_proposal is not None and not isinstance(
            blueprint_proposal, BlueprintProposal
        ):
            raise TypeError("blueprint_proposal must be a BlueprintProposal")
        unit_values = tuple(units)
        result_values = tuple(unit_results)
        if not all(isinstance(unit, ResearchWritingUnit) for unit in unit_values):
            raise TypeError("units must contain only ResearchWritingUnit values")
        if not all(isinstance(result, UnitResult) for result in result_values):
            raise TypeError("unit_results must contain only UnitResult values")
        if review_assessment is not None and not isinstance(review_assessment, ReviewAssessment):
            raise TypeError("review_assessment must be a ReviewAssessment")

        ran_research = False
        ran_prototype = False
        built_blueprint = False
        created_units = False
        submitted_results = False
        for _ in range(16):
            state = self.resume()
            if state.phase == "RESEARCH":
                if (
                    state.status == "ACTIVE"
                    and research_config is not None
                    and not ran_research
                ):
                    ran_research = True
                    self.run_research(research_config)
                    continue
                if state.status == "READY_FOR_NEXT_PHASE":
                    self.accept_research_handoff()
                    continue
                return state
            if state.phase == "PROTOTYPE":
                if (
                    state.status == "ACTIVE"
                    and prototype_submission is not None
                    and not ran_prototype
                ):
                    ran_prototype = True
                    self.run_prototype(prototype_submission)
                    continue
                if state.status == "READY_FOR_NEXT_PHASE":
                    self.accept_prototype_handoff()
                    continue
                return state
            if state.phase == "PRD":
                if (
                    state.status == "ACTIVE"
                    and blueprint_proposal is not None
                    and not built_blueprint
                ):
                    built_blueprint = True
                    self.build_review_blueprint(blueprint_proposal)
                    continue
                if state.status == "READY_FOR_NEXT_PHASE":
                    self.accept_review_blueprint()
                    continue
                return state
            if state.phase == "ISSUES":
                if (
                    state.status == "ACTIVE"
                    and unit_values
                    and not created_units
                ):
                    created_units = True
                    self.create_review_units(unit_values)
                    continue
                if state.status == "READY_FOR_NEXT_PHASE":
                    self.accept_unit_plan()
                    continue
                return state
            if state.phase == "IMPLEMENT":
                if (
                    state.status == "ACTIVE"
                    and result_values
                    and not submitted_results
                ):
                    submitted_results = True
                    self.submit_ready_unit_results(result_values)
                    continue
                if state.status == "READY_FOR_NEXT_PHASE" and review_assessment is not None:
                    return self.run_review(review_assessment, journal_adaptation)
                return state
            return state
        raise RuntimeError("Continuous cycle exceeded its phase-transition safety bound.")

    advance_continuous = run_continuous_cycle

    def export_docx(self, output_path=None, *, profile=None):
        """Export the canonical Markdown draft through the single project seam.

        Delivery remains a projection: it reads ``review-content.md`` and
        never creates a second content source or workflow state.  The import is
        local so the core orchestrator stays usable in keyless/minimal setups.
        """

        from delivery import GenericChemistryDocxExporter, JournalProfile

        if profile is None:
            profile_path = self.project_root / "journal-profile.md"
            profile = (
                JournalProfile.reconcile(self.project_root)
                if profile_path.exists()
                else JournalProfile.unselected()
            )
        if profile.status == "SELECTED" and profile.adaptation_status == "GAP":
            from delivery import DocxExportError

            error = DocxExportError(
                profile.recovery_action
                or "Journal profile is stale or unavailable; refresh the official guide before exporting."
            )
            if self.state_path.exists():
                self._update_state(
                    status="WAITING_FOR_HUMAN",
                    next_action="HUMAN_ACTION_REQUIRED: " + str(error),
                    human_action="REQUIRED",
                    open_questions=str(error),
                    resume_note="Generic Markdown remains canonical; journal adaptation must be refreshed.",
                )
            raise error
        exporter = GenericChemistryDocxExporter(self.project_root)
        try:
            return exporter.export(output_path, profile=profile)
        except Exception as error:
            from delivery import DocxExportError

            if isinstance(error, DocxExportError) and self.state_path.exists():
                self._update_state(
                    status="WAITING_FOR_HUMAN",
                    next_action=(
                        "HUMAN_ACTION_REQUIRED: preserve the existing DOCX and resolve its digest conflict "
                        "before exporting again."
                    ),
                    human_action="REQUIRED",
                    open_questions=str(error),
                    resume_note="The DOCX was not overwritten; review-content.md remains canonical.",
                )
            raise

    def retry_review_unit(self, unit_id: str) -> WorkflowResult:
        """Resume one blocked unit after its missing capability or input is addressed."""

        from units import UnitManager

        self._require_state("IMPLEMENT")
        manager = UnitManager(self.project_root, today=self.today)
        ready = manager.retry_unit(unit_id)
        self._update_state(
            status="ACTIVE",
            next_action="Retry ready units: " + ", ".join(ready),
            unit_ready=", ".join(ready) or "NONE",
            human_action="NONE",
            tool_degradation="None recorded.",
            open_questions="None recorded.",
            resume_note=f"Unit {unit_id} is ready to retry; its earlier blocked result remains in history.",
        )
        return self.resume()

    def merge_review_units(
        self, unit_ids, *, conflict_sections=(), resolutions=()
    ) -> WorkflowResult:
        """Centrally merge completed units or surface cross-unit conflicts."""

        from units import MergeHistoryEditConflict, MergeResolution, UnitManager

        self._require_state("IMPLEMENT")
        selected = tuple(unit_ids)
        decisions = tuple(resolutions)
        if not all(isinstance(item, MergeResolution) for item in decisions):
            raise TypeError("resolutions must contain only MergeResolution values")
        try:
            result = UnitManager(self.project_root, today=self.today).merge(
                selected,
                conflict_sections=tuple(conflict_sections),
                resolutions=decisions,
            )
        except MergeHistoryEditConflict as error:
            self._update_state(
                status="WAITING_FOR_HUMAN",
                next_action="Resolve the direct edit recorded for review-content.md Merge history.",
                human_action="REQUIRED",
                open_questions=str(error),
                resume_note="No unit status or content block was advanced from the untrusted merge history.",
            )
            return self.resume()
        if result.status == "CONFLICT":
            self._update_state(
                status="WAITING_FOR_HUMAN",
                next_action=(
                    "Resolve central merge conflicts for: " + ", ".join(result.conflicts)
                ),
                human_action="REQUIRED",
                open_questions="Merge conflicts: " + ", ".join(result.conflicts),
                resume_note="Unit assets are unchanged; merge-review.md holds both proposals for resolution.",
            )
        else:
            status = "READY_FOR_NEXT_PHASE" if result.all_units_merged else "ACTIVE"
            next_action = (
                "Review the single content source before entering Review."
                if result.all_units_merged
                else "Continue ready units or centrally merge other completed results."
            )
            self._update_state(
                status=status,
                next_action=next_action,
                content_revision=str(result.content_revision),
                content_digest=result.content_digest or None,
                readiness=result.readiness,
                human_action="NONE",
                open_questions=(
                    "A direct human content edit was retained and surfaced in review-content.md."
                    if result.human_edit_detected
                    else "None recorded."
                ),
                resume_note="Accepted changes were merged by the orchestrator; unit result assets remain available.",
            )
        return self.resume()

    def run_review(self, assessment, journal_adaptation) -> WorkflowResult:
        """Generate synchronized delivery views and the multi-layer Review report."""

        from review import JournalAdaptation, ReviewAssessment, ReviewRunner

        state = self._require_state("IMPLEMENT")
        if state.get("status") != "READY_FOR_NEXT_PHASE":
            raise ValueError("Implement must finish its central merge before Review.")
        if not isinstance(assessment, ReviewAssessment):
            raise TypeError("assessment must be a ReviewAssessment")
        if journal_adaptation is not None and not isinstance(journal_adaptation, JournalAdaptation):
            raise TypeError("journal_adaptation must be a JournalAdaptation")
        original_state = self.state_path.read_text(encoding="utf-8")
        runner = ReviewRunner(self.project_root, today=self.today)
        result = runner.run(assessment, journal_adaptation)
        if result.package_status == "INTEGRITY_HOLD":
            status = "WAITING_FOR_HUMAN"
            human_action = "REQUIRED"
            next_action = "Resolve the scientific-integrity hard stops in review-report.md."
        elif result.package_status == "REVISION_REQUIRED":
            status = "READY_FOR_NEXT_PHASE"
            human_action = "NONE"
            next_action = "Route the actionable Review notes to the earliest affected phase."
        else:
            status = "CANDIDATE_READY"
            human_action = "NONE"
            next_action = "Human science editor reviews the synchronized submission-candidate package."
        try:
            self._update_state(
                phase="REVIEW",
                status=status,
                next_action=next_action,
                human_action=human_action,
                package_status=result.package_status,
                review_value_status=result.value_status,
                review_integrity_status=result.integrity_status,
                delivery_synchronization=result.synchronization_status,
                delivery_source_digest=result.source_digest,
                resume_note=(
                    "Both delivery views and the Review report are saved from one content revision; "
                    "they do not claim scientific validity or journal acceptance."
                ),
            )
        except Exception:
            for name in runner.OUTPUT_NAMES:
                (self.project_root / name).unlink(missing_ok=True)
            self._write(self.state_path, original_state)
            raise
        return self.resume()

    def record_feedback(
        self,
        text: str = "",
        *,
        edited_manuscript: str | None = None,
        base_source_digest: str | None = None,
    ) -> WorkflowResult:
        """Record ordinary-language feedback and route to its earliest failed phase."""

        from feedback import FeedbackRecorder

        state = self._require_state()
        if not text.strip() and edited_manuscript is None:
            raise ValueError("Feedback requires ordinary-language text or a manuscript edit.")
        original_state = self.state_path.read_text(encoding="utf-8")
        original_intent = self.intent_path.read_text(encoding="utf-8")
        feedback_path = self.project_root / "review-feedback.md"
        original_feedback = feedback_path.read_text(encoding="utf-8") if feedback_path.exists() else None
        human_edit_dir = self.project_root / "human-edits"
        original_human_edits = (
            {path.name for path in human_edit_dir.glob("*.md")}
            if human_edit_dir.exists()
            else set()
        )
        try:
            route, revision, conflict = FeedbackRecorder(self.project_root, today=self.today).record(
                text,
                edited_manuscript=edited_manuscript,
                base_source_digest=base_source_digest,
            )
            if route.category == "INTENT":
                intent = self.intent_path.read_text(encoding="utf-8")
                prior = _section_value(intent, "Pending intent feedback")
                pending = (prior + "\n\n" if prior else "") + f"Feedback {revision}: {text.strip()}"
                self._write(self.intent_path, _set_section(intent, "Pending intent feedback", pending))
                return self._update_feedback_state(
                    phase="GRILL",
                    status="WAITING_FOR_HUMAN",
                    next_action="Confirm or reject the pending intent feedback before downstream regeneration.",
                    human_action="REQUIRED",
                    intent_confirmation="REQUIRED",
                    pending_return_phase=state.get("phase", "GRILL"),
                    feedback_revision=str(revision),
                    feedback_category=route.category,
                    feedback_earliest_phase=route.earliest_phase,
                    feedback_conflict=conflict,
                    pending_previous_intent_confirmation=state.get(
                        "intent_confirmation", "NOT_REQUIRED"
                    ),
                    feedback_next_action="Confirm the intent feedback before downstream regeneration.",
                    open_questions="Pending intent feedback requires explicit confirmation.",
                    resume_note="The previous intent remains authoritative until the human confirms this feedback.",
                )
            status = "WAITING_FOR_HUMAN" if conflict == "CONFLICT" or edited_manuscript is not None else "ACTIVE"
            human_action = "REQUIRED" if status == "WAITING_FOR_HUMAN" else "NONE"
            next_action = (
                "Resolve the preserved human edit conflict before central merge."
                if conflict == "CONFLICT"
                else f"Resume {route.earliest_phase} from the saved feedback while preserving prior assets."
            )
            return self._update_feedback_state(
                phase=route.earliest_phase,
                status=status,
                next_action=next_action,
                human_action=human_action,
                intent_confirmation=state.get("intent_confirmation", "NOT_REQUIRED"),
                feedback_revision=str(revision),
                feedback_category=route.category,
                feedback_earliest_phase=route.earliest_phase,
                feedback_conflict=conflict,
                feedback_next_action=next_action,
                open_questions=(
                    "A preserved human edit conflicts with the current source digest."
                    if conflict == "CONFLICT"
                    else "Prior research, blueprint, unit, and delivery assets are preserved."
                ),
                resume_note="Feedback is recorded in review-feedback.md; the next cycle starts at the earliest affected phase.",
            )
        except Exception:
            self._write(self.state_path, original_state)
            self._write(self.intent_path, original_intent)
            if original_feedback is None:
                feedback_path.unlink(missing_ok=True)
            else:
                feedback_path.write_text(original_feedback, encoding="utf-8")
            if human_edit_dir.exists():
                for path in human_edit_dir.glob("*.md"):
                    if path.name not in original_human_edits:
                        path.unlink(missing_ok=True)
            raise

    def confirm_feedback(self, *, accept: bool) -> WorkflowResult:
        """Accept or reject pending natural-language intent feedback."""

        state = self._require_state()
        if state.get("feedback_category") != "INTENT" or state.get("intent_confirmation") != "REQUIRED":
            raise ValueError("There is no pending intent feedback to confirm.")
        intent = self.intent_path.read_text(encoding="utf-8")
        pending = _section_value(intent, "Pending intent feedback")
        if not pending:
            raise ValueError("Pending intent feedback is missing or malformed.")
        original_state = self.state_path.read_text(encoding="utf-8")
        original_intent = intent
        try:
            if accept:
                revision = int(state.get("intent_revision", "0")) + 1
                intent = _set_section(intent, "Confirmed intent feedback", pending)
                intent = _remove_section(intent, "Pending intent feedback")
                intent = _replace_frontmatter(
                    intent, {"intent_revision": str(revision), "confirmation": "CONFIRMED"}
                )
                self._write(self.intent_path, intent)
                phase = "GRILL"
                next_action = "Revisit Grill using the confirmed intent feedback before downstream regeneration."
                resume_note = "The intent revision is confirmed; downstream assets remain preserved until Grill is revisited."
            else:
                intent = _remove_section(intent, "Pending intent feedback")
                self._write(self.intent_path, intent)
                revision = int(state.get("intent_revision", "0"))
                phase = state.get("pending_return_phase", "GRILL")
                next_action = f"Resume {phase} from the saved state; the intent feedback was rejected."
                resume_note = "The proposed intent change was rejected; the prior intent remains authoritative."
            restored_confirmation = (
                "CONFIRMED"
                if accept
                else state.get("pending_previous_intent_confirmation", "NOT_REQUIRED")
            )
            return self._update_feedback_state(
                phase=phase,
                status="ACTIVE",
                next_action=next_action,
                human_action="NONE",
                intent_revision=str(revision),
                intent_confirmation=restored_confirmation,
                pending_return_phase=None,
                pending_previous_intent_confirmation=None,
                feedback_requires_confirmation="NONE",
                feedback_next_action=next_action,
                open_questions="None recorded.",
                resume_note=resume_note,
            )
        except Exception:
            self._write(self.state_path, original_state)
            self._write(self.intent_path, original_intent)
            raise

    def resume_cycle(self, *, review_assessment=None, journal_adaptation=None) -> WorkflowResult:
        """Resume only the routed phase; optionally regenerate Review delivery views."""

        from feedback import FeedbackRecorder

        state = self._require_state()
        metadata = FeedbackRecorder(self.project_root, today=self.today).latest()
        if state.get("intent_confirmation") == "REQUIRED" and metadata.get("feedback_category") == "INTENT":
            return self.resume()
        if metadata.get("feedback_conflict") == "CONFLICT":
            return self.resume()
        target = metadata.get("feedback_earliest_phase", state.get("phase", "REVIEW"))
        if (
            metadata.get("feedback_category") == "INTENT"
            and state.get("feedback_requires_confirmation") == "NONE"
        ):
            target = state.get("phase", "REVIEW")
        if target == "REVIEW" and review_assessment is not None and journal_adaptation is not None:
            history_dir = self.project_root / "review-history" / f"feedback-{metadata.get('feedback_revision', 'unknown')}"
            from review import ReviewRunner

            existing_history = [
                name for name in ReviewRunner.OUTPUT_NAMES if (history_dir / name).exists()
            ]
            if existing_history:
                raise FileExistsError(
                    "review history already exists: " + ", ".join(existing_history)
                )
            history_dir.mkdir(parents=True, exist_ok=True)

            original_state = self.state_path.read_text(encoding="utf-8")
            moved: list[tuple[Path, Path]] = []
            try:
                for name in ReviewRunner.OUTPUT_NAMES:
                    output = self.project_root / name
                    archived = history_dir / name
                    if output.exists():
                        shutil.move(str(output), str(archived))
                        moved.append((output, archived))
                self._update_state(
                    phase="IMPLEMENT",
                    status="READY_FOR_NEXT_PHASE",
                    next_action="Regenerate synchronized Review delivery views from the preserved content source.",
                    human_action="NONE",
                    resume_note="Only the Review/delivery tail is being rerun; Research, blueprint, units, and content source are preserved.",
                )
                return self.run_review(review_assessment, journal_adaptation)
            except Exception:
                for output, archived in reversed(moved):
                    if archived.exists():
                        archived.replace(output)
                self._write(self.state_path, original_state)
                raise
        return self._update_feedback_state(
            phase=target,
            status="ACTIVE",
            next_action=f"Resume {target} using the saved feedback and preserved upstream assets.",
            human_action="NONE",
            feedback_next_action=f"Resume {target} using the saved feedback and preserved upstream assets.",
            resume_note="This is a partial rerun boundary; unaffected upstream assets are preserved.",
        )

    def _update_feedback_state(self, **updates: str | None) -> WorkflowResult:
        self._update_state(**updates)
        return self.resume()

    def propose_intent_change(
        self, changes: Mapping[str, str], *, earliest_phase: str = "GRILL"
    ) -> WorkflowResult:
        """Hold a core-intent change for explicit human confirmation."""

        state = self._require_state()
        if earliest_phase not in PHASES:
            raise ValueError(f"Unknown workflow phase: {earliest_phase}")
        normalized = self._normalize_answers(changes)
        proposals = {
            key: value
            for key, value in normalized.items()
            if (key in _INTENT_HEADINGS or key == "exclusions") and value.strip()
        }
        if not proposals:
            raise ValueError("At least one core-intent change is required.")
        proposal_body = "\n".join(
            f"- {key}: {value}" for key, value in proposals.items()
        )
        intent = self.intent_path.read_text(encoding="utf-8")
        intent = _set_section(intent, "Pending intent change", proposal_body)
        self._write(self.intent_path, intent)
        self._update_state(
            status="WAITING_FOR_HUMAN",
            next_action="Confirm or reject the pending intent change in ordinary language.",
            intent_confirmation="REQUIRED",
            human_action="REQUIRED",
            pending_previous_intent_confirmation=state.get("intent_confirmation", "NOT_REQUIRED"),
            resume_note=f"The proposal affects {earliest_phase}; downstream assets remain unchanged.",
            pending_earliest_phase=earliest_phase,
        )
        return self.resume()

    def confirm_intent_change(self, *, accept: bool) -> WorkflowResult:
        """Accept or reject a pending intent change without losing its history."""

        state = self._require_state()
        if state.get("intent_confirmation") != "REQUIRED":
            raise ValueError("There is no pending intent change to confirm.")
        intent = self.intent_path.read_text(encoding="utf-8")
        pending = _section_value(intent, "Pending intent change")
        proposals = _parse_bullets(pending)
        if not proposals:
            raise ValueError("The pending intent change is empty or malformed.")
        earliest_phase = state.get("pending_earliest_phase", "GRILL")
        if accept:
            revision = int(state.get("intent_revision", "0"))
            history = "\n".join(
                f"- Revision {revision} before change: {key} = "
                f"{_section_value(intent, _INTENT_HEADINGS.get(key, 'Scope and exclusions'))}"
                for key in proposals
            )
            intent = _set_section(intent, "Intent revision history", history)
            intent = self._apply_intent_answers(intent, proposals)
            intent = self._apply_journal_answers(intent, proposals)
            intent = _remove_section(intent, "Pending intent change")
            journal_change = "target_journal" in proposals
            if journal_change:
                intent = _replace_frontmatter(
                    intent,
                    {
                        "target_journal": proposals["target_journal"],
                        "journal_status": "SELECTED",
                        "journal_confirmation": "CONFIRMED",
                    },
                )
                intent = _remove_frontmatter_keys(intent, ("journal_guide_locator",))
            intent = _replace_frontmatter(intent, {"intent_revision": str(revision + 1), "confirmation": "CONFIRMED"})
            self._write(self.intent_path, intent)
            self._update_state(
                phase=earliest_phase,
                status="ACTIVE",
                next_action=f"Revisit {earliest_phase} with the confirmed intent change.",
                intent_revision=str(revision + 1),
                intent_confirmation="CONFIRMED",
                human_action="NONE",
                journal_status="SELECTED" if journal_change else state.get("journal_status"),
                journal_confirmation=(
                    "CONFIRMED" if journal_change else state.get("journal_confirmation")
                ),
                journal_guide_status=(
                    "NONE" if journal_change else state.get("journal_guide_status")
                ),
                journal_guide_digest=(
                    None if journal_change else state.get("journal_guide_digest")
                ),
                pending_previous_intent_confirmation=None,
                resume_note="The accepted change is routed to the earliest affected phase.",
                pending_earliest_phase=None,
            )
        else:
            intent = _remove_section(intent, "Pending intent change")
            self._write(self.intent_path, intent)
            self._update_state(
                status="ACTIVE",
                next_action=f"Continue {state.get('phase', 'GRILL')} from the saved state.",
                intent_confirmation=state.get("pending_previous_intent_confirmation", state.get("intent_confirmation", "NOT_REQUIRED")),
                human_action="NONE",
                pending_previous_intent_confirmation=None,
                resume_note="The proposed change was rejected; the prior intent remains authoritative.",
                pending_earliest_phase=None,
            )
        return self.resume()

    def _write_initial_assets(
        self,
        topic: str,
        *,
        execution_mode: str = "acceptance",
        materials: Mapping[str, str | Path] | Sequence[str | Path] | None = None,
    ) -> None:
        material_sections = self._extract_known_materials(materials)
        known_question = material_sections.get("Research question", "").strip()
        if known_question and not _is_open(known_question):
            topic = known_question
        known_facts = self._render_known_facts(material_sections)
        researcher_context = material_sections.get(
            "Researcher context and prior knowledge", "Open question: provide only decision-relevant background."
        )
        evidence_standards = material_sections.get(
            "Evidence standards and constraints",
            "Open question: specify source types, experimental details, and practical constraints.",
        )
        default_scope = (
            "Scope: Open question: define the included chemistry.\n"
            "Exclusions: Open question: define what is out of scope."
        )
        frontier = self._render_frontier_questions(
            topic=topic,
            known=material_sections,
            include_heading=True,
        )
        intent = _document(
            {
                "kind": "review-intent",
                "schema": "1",
                "intent_revision": "0",
                "confirmation": "REQUIRED",
                "journal_status": "UNSET",
                "journal_confirmation": "REQUIRED",
            },
            "# Review Intent\n\n"
            f"## Research question\n{topic}\n\n"
            f"## Core-claim candidates\n{material_sections.get('Core-claim candidates', 'Open question: propose one or more non-trivial claims.')}\n\n"
            f"## Scope and exclusions\n{material_sections.get('Scope and exclusions', default_scope)}\n\n"
            f"## Audience or target journal\n{material_sections.get('Audience or target journal', 'Open question: identify the intended reader or journal.')}\n\n"
            "## Journal candidates\nNone recorded.\n\n"
            f"## Expected contribution\n{material_sections.get('Expected contribution', 'Open question: explain why this review matters now.')}\n\n"
            f"## Known facts\n{known_facts}\n\n"
            f"## Researcher context and prior knowledge\n{researcher_context}\n\n"
            f"## Evidence standards and constraints\n{evidence_standards}\n\n"
            f"## Frontier interview\n{frontier}\n\n"
            f"## Open questions\n{frontier}",
        )
        domain = _document(
            {"kind": "domain-profile", "schema": "1"},
            "# Project Domain Profile\n\n"
            "## Chemical subfield\nOpen question: identify the relevant chemical subfield.\n\n"
            "## Core systems\nOpen question: identify the molecules, reactions, materials, devices, or analytical objects.\n\n"
            "## Canonical terms and synonyms\n"
            f"Initial topic: {topic}\n\n"
            f"## Boundary scenarios\n{material_sections.get('Boundary scenarios', 'Open question: identify edge cases that affect scope or comparability.')}\n\n"
            f"## Evidence expectations\n{material_sections.get('Evidence expectations', 'Open question: decide which source types and experimental details are required.')}\n\n"
            "## Known capability limits\nRecord tool or source limits as they are discovered.\n",
        )
        state = _document(
            {
                "kind": "chemical-review-workflow-state",
                "schema": "1",
                "phase": "GRILL",
                "status": "ACTIVE",
                "next_action": "Answer only the current Grill frontier questions recorded in review-intent.md; confirm the research question only if it remains open.",
                "intent_revision": "0",
                "intent_confirmation": "REQUIRED",
                "journal_status": "UNSET",
                "journal_confirmation": "REQUIRED",
                "execution_mode": execution_mode,
                "human_action": "NONE",
                "updated": self.today.isoformat(),
            },
            "# Workflow State\n\n"
            "## Current goal\nClarify the review intent before literature research.\n\n"
            "## Recently completed\nCreated the initial topic-only project assets.\n\n"
            "## Open questions and risks\n"
            f"{frontier}\n\n"
            "## Tool degradation or HUMAN_ACTION_REQUIRED\nNone.\n\n"
            "## Resume note\nThe next invocation continues Grill from these Markdown assets.\n",
        )
        self._write(self.intent_path, intent)
        self._write(self.domain_path, domain)
        self._write(self.state_path, state)

    def _normalize_answers(self, answers: Mapping[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_key, raw_value in answers.items():
            key = _ALIASES.get(raw_key.strip().lower())
            if key is None or not isinstance(raw_value, str) or not raw_value.strip():
                continue
            normalized[key] = raw_value.strip()
        return normalized

    def _extract_known_materials(
        self,
        materials: Mapping[str, str | Path] | Sequence[str | Path] | None,
    ) -> dict[str, str]:
        """Extract decision-relevant sections without copying unrelated notes."""

        entries: list[tuple[str, str]] = []
        if materials is None:
            # A topic-only start must not rummage through project files.  The
            # caller has to explicitly provide proposal/search-log/PDF-manifest
            # material, keeping private history and logs outside the read set.
            materials = ()
        if isinstance(materials, Mapping):
            iterable = materials.items()
        else:
            iterable = ((str(value), value) for value in materials)
        for label, value in iterable:
            text: str
            if isinstance(value, Path):
                path = value
                if not path.exists() or path.suffix.lower() == ".pdf":
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
            elif isinstance(value, str):
                possible_path = Path(value)
                try:
                    is_path = possible_path.exists() and possible_path.suffix.lower() != ".pdf"
                except OSError:
                    is_path = False
                if is_path:
                    try:
                        text = possible_path.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        continue
                else:
                    text = value
            else:
                continue
            entries.append((str(label), text))

        result: dict[str, str] = {}
        for label, text in entries:
            sections = self._material_sections(text)
            if not sections:
                safe = self._scrub_decision_text(text)
                if safe:
                    result.setdefault(f"Material: {label}", safe)
                continue
            for heading, body in sections.items():
                canonical = self._canonical_material_heading(heading)
                safe = self._scrub_decision_text(body)
                if not safe:
                    continue
                if canonical in result and safe not in result[canonical]:
                    result[canonical] = result[canonical].rstrip() + "\n" + safe
                else:
                    result.setdefault(canonical, safe)
        return result

    @staticmethod
    def _material_sections(text: str) -> dict[str, str]:
        headings = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", text))
        if not headings:
            return {}
        sections: dict[str, str] = {}
        for index, match in enumerate(headings):
            start = match.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            sections[match.group(1).strip()] = text[start:end].strip()
        return sections

    @staticmethod
    def _canonical_material_heading(heading: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", " ", heading.lower()).strip()
        aliases = {
            "question": "Research question",
            "research question": "Research question",
            "core claim": "Core-claim candidates",
            "core claims": "Core-claim candidates",
            "core claim candidates": "Core-claim candidates",
            "scope": "Scope and exclusions",
            "scope and exclusions": "Scope and exclusions",
            "exclusions": "Scope and exclusions",
            "audience": "Audience or target journal",
            "audience or target journal": "Audience or target journal",
            "target reader": "Audience or target journal",
            "target journal": "Audience or target journal",
            "expected contribution": "Expected contribution",
            "value hypothesis": "Expected contribution",
            "researcher background": "Researcher context and prior knowledge",
            "background": "Researcher context and prior knowledge",
            "prior knowledge": "Researcher context and prior knowledge",
            "researcher context and prior knowledge": "Researcher context and prior knowledge",
            "evidence standards": "Evidence standards and constraints",
            "evidence expectations": "Evidence standards and constraints",
            "constraints": "Evidence standards and constraints",
            "evidence standards and constraints": "Evidence standards and constraints",
            "boundary scenarios": "Boundary scenarios",
            "controversies": "Frontier interview",
            "research preferences": "Frontier interview",
            "search preferences": "Frontier interview",
            "chemical subfield": "Chemical subfield",
            "core systems": "Core systems",
            "canonical terms and synonyms": "Canonical terms and synonyms",
        }
        return aliases.get(normalized, heading.strip())

    @staticmethod
    def _scrub_decision_text(value: str) -> str:
        safe_lines: list[str] = []
        sensitive = re.compile(
            r"(?:password|passwd|token|api[_ -]?key|secret|cookie|session|private key|email\s*:|e-mail\s*:)",
            re.IGNORECASE,
        )
        for line in value.splitlines():
            if sensitive.search(line):
                continue
            stripped = line.strip()
            if stripped:
                safe_lines.append(stripped)
        return "\n".join(safe_lines)

    @staticmethod
    def _render_known_facts(sections: Mapping[str, str]) -> str:
        facts = [
            f"- {heading}: {value}"
            for heading, value in sections.items()
            if heading not in {"Frontier interview", "Known facts"}
            and value.strip()
            and not _is_open(value)
        ]
        return "\n".join(facts) or "No project facts extracted yet."

    def _render_frontier_questions(
        self,
        *,
        topic: str,
        known: Mapping[str, str],
        include_heading: bool = False,
    ) -> str:
        questions: list[str] = []
        claims = known.get("Core-claim candidates", "")
        scope = known.get("Scope and exclusions", "")
        audience = known.get("Audience or target journal", "")
        contribution = known.get("Expected contribution", "")
        evidence = known.get("Evidence standards and constraints", "")
        context = known.get("Researcher context and prior knowledge", "")
        boundary = known.get("Boundary scenarios", "")
        if _is_open(claims):
            questions.append("- Frontier question: Which non-trivial core claim candidate should Research challenge first?")
        if _is_open(_labeled_value(scope, "Scope")):
            questions.append("- Frontier question: What chemistry is in scope, including the systems or time boundary?")
        if _is_open(_labeled_value(scope, "Exclusions")):
            questions.append("- Frontier question: Which adjacent systems or claims are explicitly excluded?")
        if _is_open(audience):
            questions.append("- Frontier question: Who is the target reader, or which journal should guide the format?")
        if _is_open(contribution):
            questions.append("- Frontier question: What decision or understanding should this review change now?")
        if _is_open(evidence):
            questions.append("- Frontier question: Which evidence standards, source types, and experimental details are required?")
        if _is_open(context):
            questions.append("- Frontier question: What decision-relevant background or prior knowledge should shape the search route?")
        if _is_open(boundary):
            questions.append("- Frontier question: Which boundary scenarios could change comparability or the stopping decision?")
        if not questions:
            questions.append("- No frontier gap detected; review the saved intent and confirm it before Research.")
        if include_heading:
            return "\n".join(questions)
        return "\n".join(questions)

    def _frontier_questions_from_assets(self) -> list[str]:
        if not self.intent_path.exists() or not self.domain_path.exists():
            return []
        intent = self.intent_path.read_text(encoding="utf-8")
        domain = self.domain_path.read_text(encoding="utf-8")
        known = {
            heading: _section_value(intent, heading)
            for heading in (
                "Core-claim candidates",
                "Scope and exclusions",
                "Audience or target journal",
                "Expected contribution",
                "Evidence standards and constraints",
                "Researcher context and prior knowledge",
            )
        }
        known.update(
            {
                "Boundary scenarios": _section_value(domain, "Boundary scenarios"),
            }
        )
        return self._render_frontier_questions(
            topic=_section_value(intent, "Research question"), known=known
        ).splitlines()

    def _known_facts_from_intent(self) -> list[str]:
        if not self.intent_path.exists():
            return []
        value = _section_value(
            self.intent_path.read_text(encoding="utf-8"), "Known facts"
        )
        return [line.strip() for line in value.splitlines() if line.strip()]

    def _ingest_known_materials(
        self, materials: Mapping[str, str | Path] | Sequence[str | Path]
    ) -> None:
        extracted = self._extract_known_materials(materials)
        if not extracted:
            return
        intent = self.intent_path.read_text(encoding="utf-8")
        domain = self.domain_path.read_text(encoding="utf-8")
        for heading in (
            "Research question",
            "Core-claim candidates",
            "Scope and exclusions",
            "Audience or target journal",
            "Expected contribution",
            "Researcher context and prior knowledge",
            "Evidence standards and constraints",
            "Frontier interview",
        ):
            value = extracted.get(heading)
            if value and _is_open(_section_value(intent, heading)):
                intent = _set_section(intent, heading, value)
        existing_facts = _section_value(intent, "Known facts")
        facts = self._render_known_facts(extracted)
        intent = _set_section(intent, "Known facts", _merge_unique_lines(existing_facts, facts))
        for heading in (
            "Chemical subfield",
            "Core systems",
            "Canonical terms and synonyms",
            "Boundary scenarios",
            "Evidence expectations",
        ):
            value = extracted.get(heading)
            if value and _is_open(_section_value(domain, heading)):
                domain = _set_section(domain, heading, value)
        self._write(self.intent_path, intent)
        self._write(self.domain_path, domain)
        frontier = "\n".join(self._frontier_questions_from_assets())
        self._update_state(
            next_action="Answer only the current Grill frontier questions recorded in review-intent.md; confirm the research question only if it remains open.",
            open_questions=frontier,
            resume_note="Known project materials were extracted; unrelated private notes were not collected.",
        )

    @staticmethod
    def _normalize_execution_mode(mode: str | None) -> str | None:
        if mode is None:
            return None
        normalized = mode.strip().lower()
        if normalized not in EXECUTION_MODES:
            raise ValueError(
                "execution mode must be one of: " + ", ".join(EXECUTION_MODES)
            )
        return normalized

    def _apply_intent_answers(self, intent: str, answers: Mapping[str, str]) -> str:
        for key, heading in _INTENT_HEADINGS.items():
            if key in answers:
                if key == "scope":
                    current = _section_value(intent, heading)
                    exclusions = _labeled_value(current, "Exclusions") or "Open question: define what is out of scope."
                    intent = _set_section(intent, heading, f"Scope: {answers[key]}\nExclusions: {exclusions}")
                else:
                    intent = _set_section(intent, heading, answers[key])
        if "exclusions" in answers:
            current = _section_value(intent, "Scope and exclusions")
            scope = _labeled_value(current, "Scope") or "Open question: define the included chemistry."
            intent = _set_section(intent, "Scope and exclusions", f"Scope: {scope}\nExclusions: {answers['exclusions']}")
        return intent

    def _apply_journal_answers(self, intent: str, answers: Mapping[str, str]) -> str:
        if "target_journal" not in answers:
            return intent
        current = _section_value(intent, "Audience or target journal")
        target_reader = _labeled_value(current, "Target reader")
        reader_line = f"Target reader: {target_reader}\n" if target_reader else ""
        guide = answers.get("journal_guide_locator", "")
        guide_line = f"Official guide: {guide}\n" if guide else ""
        return _set_section(
            intent,
            "Audience or target journal",
            f"{reader_line}Target journal: {answers['target_journal']}\n{guide_line}".rstrip(),
        )

    def _apply_domain_answers(self, domain: str, answers: Mapping[str, str]) -> str:
        for key, heading in _DOMAIN_HEADINGS.items():
            if key in answers:
                domain = _set_section(domain, heading, answers[key])
        return domain

    def _missing_intent_fields(self, intent: str) -> list[str]:
        missing: list[str] = []
        if _is_open(_section_value(intent, "Core-claim candidates")):
            missing.append("Core-claim candidates")
        scope = _section_value(intent, "Scope and exclusions")
        if _is_open(_labeled_value(scope, "Scope")):
            missing.append("Scope")
        if _is_open(_labeled_value(scope, "Exclusions")):
            missing.append("Exclusions")
        if _is_open(_section_value(intent, "Expected contribution")):
            missing.append("Expected contribution")
        return missing

    def _require_state(self, phase: str | None = None) -> dict[str, str]:
        if not self.state_path.exists():
            raise FileNotFoundError(f"No workflow state at {self.state_path}")
        metadata, _ = _split_frontmatter(self.state_path.read_text(encoding="utf-8"))
        if phase and metadata.get("phase") != phase:
            raise ValueError(f"This action requires phase {phase}, found {metadata.get('phase')}")
        return metadata

    def _execution_mode(self) -> str:
        mode = self._require_state().get("execution_mode", "acceptance")
        if mode not in EXECUTION_MODES:
            raise ValueError(f"Unknown persisted execution mode: {mode}")
        return mode

    def _update_state(self, **updates: str | None) -> None:
        metadata, body = _split_frontmatter(self.state_path.read_text(encoding="utf-8"))
        for key, value in updates.items():
            if key in {"open_questions", "resume_note", "tool_degradation"}:
                continue
            if value is None:
                metadata.pop(key, None)
            else:
                metadata[key] = value
        metadata["updated"] = self.today.isoformat()
        open_questions = updates.get("open_questions")
        if open_questions is None:
            open_questions = _section_value(body, "Open questions and risks")
        resume_note = updates.get("resume_note")
        if resume_note is None:
            resume_note = _section_value(body, "Resume note")
        tool_degradation = updates.get("tool_degradation")
        if tool_degradation is None:
            tool_degradation = _section_value(body, "Tool degradation or HUMAN_ACTION_REQUIRED")
        body = _set_section(body, "Open questions and risks", open_questions)
        body = _set_section(body, "Resume note", resume_note)
        body = _set_section(body, "Tool degradation or HUMAN_ACTION_REQUIRED", tool_degradation)
        self._write(self.state_path, _document(metadata, body))

    def _write(self, path: Path, content: str) -> None:
        path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _document(metadata: Mapping[str, str], body: str) -> str:
    frontmatter = "---\n" + "\n".join(
        f"{key}: {_encode_frontmatter_value(value)}"
        for key, value in metadata.items()
    ) + "\n---\n\n"
    return frontmatter + body.lstrip()


def _encode_frontmatter_value(value: object) -> str:
    """Keep scalar frontmatter on one line; body sections carry paragraphs."""

    return str(value).replace("\\", "\\\\").replace("\n", "\\n")


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("Markdown asset must begin with frontmatter.")
    end = text.find("\n---", 4)
    if end < 0:
        raise ValueError("Markdown asset has unterminated frontmatter.")
    raw = text[4:end]
    metadata: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"Malformed frontmatter line: {line}")
        metadata[key.strip()] = value.strip().replace("\\n", "\n").replace("\\\\", "\\")
    return metadata, text[end + len("\n---") :].lstrip("\n")


def _replace_frontmatter(text: str, updates: Mapping[str, str]) -> str:
    metadata, body = _split_frontmatter(text)
    metadata.update(updates)
    return _document(metadata, body)


def _remove_frontmatter_keys(text: str, keys: Sequence[str]) -> str:
    metadata, body = _split_frontmatter(text)
    for key in keys:
        metadata.pop(key, None)
    return _document(metadata, body)


def _section_pattern(title: str) -> re.Pattern[str]:
    return re.compile(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)


def _section_value(text: str, title: str) -> str:
    body = _split_frontmatter(text)[1] if text.startswith("---\n") else text
    match = _section_pattern(title).search(body)
    if not match:
        return ""
    value = re.sub(r"<!--.*?-->", "", match.group(1), flags=re.DOTALL).strip()
    return value


def _set_section(text: str, title: str, value: str) -> str:
    has_frontmatter = text.startswith("---\n")
    if has_frontmatter:
        metadata, body = _split_frontmatter(text)
    else:
        metadata, body = {}, text
    replacement = f"## {title}\n{value.strip()}\n\n"
    pattern = _section_pattern(title)
    if pattern.search(body):
        body = pattern.sub(lambda _: replacement, body, count=1)
    else:
        body = body.rstrip() + "\n\n" + replacement
    return _document(metadata, body) if has_frontmatter else body.lstrip()


def _remove_section(text: str, title: str) -> str:
    has_frontmatter = text.startswith("---\n")
    if has_frontmatter:
        metadata, body = _split_frontmatter(text)
    else:
        metadata, body = {}, text
    body = _section_pattern(title).sub("", body, count=1)
    return _document(metadata, body) if has_frontmatter else body.lstrip()


def _labeled_value(value: str, label: str) -> str:
    match = re.search(rf"(?:^|\n){re.escape(label)}:\s*(.*?)(?=\n[A-Z][^:\n]+:|\Z)", value, re.DOTALL)
    return match.group(1).strip() if match else ""


def _is_open(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or normalized.startswith("open question") or normalized.startswith("<")


def _merge_unique_lines(existing: str, generated: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for line in (existing + "\n" + generated).splitlines():
        value = line.strip()
        if value and value not in seen:
            seen.add(value)
            lines.append(line)
    return "\n".join(lines) or "No project facts extracted yet."


def _parse_bullets(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in value.splitlines():
        if not line.lstrip().startswith("-"):
            continue
        key, separator, item = line.lstrip()[1:].partition(":")
        if separator and (key.strip() in _INTENT_HEADINGS or key.strip() == "exclusions"):
            parsed[key.strip()] = item.strip()
    return parsed


def _target_journal_from_intent(intent: str) -> str:
    metadata, _ = _split_frontmatter(intent) if intent.startswith("---\n") else ({}, intent)
    target = metadata.get("target_journal", "").strip()
    if target:
        return target
    audience = _section_value(intent, "Audience or target journal")
    return _labeled_value(audience, "Target journal")


def _parse_journal_candidates(value: str):
    from review import JournalCandidate

    candidates: list[JournalCandidate] = []
    current: dict[str, str] = {}
    for line in value.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Journal:"):
            if current:
                candidates.append(
                    JournalCandidate(
                        current.get("target_journal", ""),
                        current.get("rationale", ""),
                        current.get("official_guide_locator", ""),
                    )
                )
            current = {"target_journal": stripped.split(":", 1)[1].strip()}
        elif stripped.startswith("Rationale:"):
            current["rationale"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Official guide:"):
            current["official_guide_locator"] = stripped.split(":", 1)[1].strip()
    if current:
        candidates.append(
            JournalCandidate(
                current.get("target_journal", ""),
                current.get("rationale", ""),
                current.get("official_guide_locator", ""),
            )
        )
    return tuple(candidates)
