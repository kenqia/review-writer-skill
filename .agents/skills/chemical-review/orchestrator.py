"""Small, file-backed orchestrator for the chemical-review skill.

The orchestrator owns phase transitions and the central merge boundary while
stage modules own their human-readable Markdown assets. Keeping this seam
executable makes start/resume, confirmation, dependency, and write-ownership
boundaries testable without introducing a service or a second state store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
import shutil
from typing import Mapping


PHASES = ("GRILL", "RESEARCH", "PROTOTYPE", "PRD", "ISSUES", "IMPLEMENT", "REVIEW")
STATUSES = ("ACTIVE", "WAITING_FOR_HUMAN", "READY_FOR_NEXT_PHASE", "CANDIDATE_READY")

_INTENT_HEADINGS = {
    "research_question": "Research question",
    "core_claim_candidates": "Core-claim candidates",
    "scope": "Scope and exclusions",
    "audience": "Audience or target journal",
    "expected_contribution": "Expected contribution",
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
    "journal": "audience",
    "audience_or_target_journal": "audience",
    "contribution": "expected_contribution",
    "expected_contribution": "expected_contribution",
    "chemical_subfield": "chemical_subfield",
    "core_systems": "core_systems",
    "terms": "terms",
    "canonical_terms": "terms",
    "boundary_scenarios": "boundary_scenarios",
    "evidence_expectations": "evidence_expectations",
    "known_capability_limits": "known_capability_limits",
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

    def start(self, topic: str) -> WorkflowResult:
        """Start from a topic, or resume if this project already has state."""

        if self.state_path.exists():
            return self.resume()
        topic = topic.strip()
        if not topic:
            raise ValueError("A chemistry review topic or research idea is required.")

        self._write_initial_assets(topic)
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
        )

    def continue_grill(self, answers: Mapping[str, str]) -> WorkflowResult:
        """Apply ordinary-language Grill answers without guessing omissions."""

        self._require_state("GRILL")
        intent = self.intent_path.read_text(encoding="utf-8")
        domain = self.domain_path.read_text(encoding="utf-8")
        normalized = self._normalize_answers(answers)
        intent = self._apply_intent_answers(intent, normalized)
        domain = self._apply_domain_answers(domain, normalized)
        missing = self._missing_intent_fields(intent)
        open_questions = "None recorded." if not missing else "\n".join(f"- {item}" for item in missing)
        intent = _set_section(intent, "Open questions", open_questions)
        self._write(self.intent_path, intent)
        self._write(self.domain_path, domain)

        if missing:
            self._update_state(
                status="ACTIVE",
                next_action="continue Grill by answering the open questions in review-intent.md.",
                intent_confirmation="REQUIRED",
                human_action="NONE",
                open_questions=open_questions,
                resume_note="The project remains in Grill until the core intent is clear.",
            )
        else:
            self._update_state(
                status="READY_FOR_NEXT_PHASE",
                next_action="Confirm the Grill contract before starting Research.",
                intent_confirmation="REQUIRED",
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
        intent = self.intent_path.read_text(encoding="utf-8")
        intent = _replace_frontmatter(intent, {"confirmation": "CONFIRMED"})
        self._write(self.intent_path, intent)
        self._update_state(
            phase="RESEARCH",
            status="ACTIVE",
            next_action="Build the research evidence packet from the confirmed intent.",
            intent_confirmation="CONFIRMED",
            human_action="NONE",
            resume_note="Research is the first downstream phase after the confirmed Grill contract.",
        )
        return self.resume()

    def run_research(self, config=None) -> WorkflowResult:
        """Run or rerun Research with replaceable adapters and persist its assets."""

        from research import ResearchConfig, ResearchRunner

        self._require_state("RESEARCH")
        if config is None:
            config = ResearchConfig()
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
        if not isinstance(journal_adaptation, JournalAdaptation):
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

        self._require_state()
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
            intent = _remove_section(intent, "Pending intent change")
            intent = _replace_frontmatter(intent, {"intent_revision": str(revision + 1), "confirmation": "CONFIRMED"})
            self._write(self.intent_path, intent)
            self._update_state(
                phase=earliest_phase,
                status="ACTIVE",
                next_action=f"Revisit {earliest_phase} with the confirmed intent change.",
                intent_revision=str(revision + 1),
                intent_confirmation="CONFIRMED",
                human_action="NONE",
                resume_note="The accepted change is routed to the earliest affected phase.",
                pending_earliest_phase=None,
            )
        else:
            intent = _remove_section(intent, "Pending intent change")
            self._write(self.intent_path, intent)
            self._update_state(
                status="ACTIVE",
                next_action=f"Continue {state.get('phase', 'GRILL')} from the saved state.",
                intent_confirmation="CONFIRMED",
                human_action="NONE",
                resume_note="The proposed change was rejected; the prior intent remains authoritative.",
                pending_earliest_phase=None,
            )
        return self.resume()

    def _write_initial_assets(self, topic: str) -> None:
        intent = _document(
            {
                "kind": "review-intent",
                "schema": "1",
                "intent_revision": "0",
                "confirmation": "REQUIRED",
            },
            "# Review Intent\n\n"
            f"## Research question\n{topic}\n\n"
            "## Core-claim candidates\nOpen question: propose one or more non-trivial claims.\n\n"
            "## Scope and exclusions\nScope: Open question: define the included chemistry.\n"
            "Exclusions: Open question: define what is out of scope.\n\n"
            "## Audience or target journal\nOpen question: identify the intended reader or journal.\n\n"
            "## Expected contribution\nOpen question: explain why this review matters now.\n\n"
            "## Open questions\n- Core claim\n- Scope and exclusions\n- Audience or target journal\n- Expected contribution\n",
        )
        domain = _document(
            {"kind": "domain-profile", "schema": "1"},
            "# Project Domain Profile\n\n"
            "## Chemical subfield\nOpen question: identify the relevant chemical subfield.\n\n"
            "## Core systems\nOpen question: identify the molecules, reactions, materials, devices, or analytical objects.\n\n"
            "## Canonical terms and synonyms\n"
            f"Initial topic: {topic}\n\n"
            "## Boundary scenarios\nOpen question: identify edge cases that affect scope or comparability.\n\n"
            "## Evidence expectations\nOpen question: decide which source types and experimental details are required.\n\n"
            "## Known capability limits\nRecord tool or source limits as they are discovered.\n",
        )
        state = _document(
            {
                "kind": "chemical-review-workflow-state",
                "schema": "1",
                "phase": "GRILL",
                "status": "ACTIVE",
                "next_action": "Answer the Grill research question, core-claim, scope/exclusions, audience/journal, and contribution prompts.",
                "intent_revision": "0",
                "intent_confirmation": "REQUIRED",
                "human_action": "NONE",
                "updated": self.today.isoformat(),
            },
            "# Workflow State\n\n"
            "## Current goal\nClarify the review intent before literature research.\n\n"
            "## Recently completed\nCreated the initial topic-only project assets.\n\n"
            "## Open questions and risks\nThe Grill prompts are intentionally unresolved.\n\n"
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
        if _is_open(_section_value(intent, "Audience or target journal")):
            missing.append("Audience or target journal")
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


def _parse_bullets(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in value.splitlines():
        if not line.lstrip().startswith("-"):
            continue
        key, separator, item = line.lstrip()[1:].partition(":")
        if separator and (key.strip() in _INTENT_HEADINGS or key.strip() == "exclusions"):
            parsed[key.strip()] = item.strip()
    return parsed
