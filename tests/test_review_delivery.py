from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "chemical-review"
sys.path.insert(0, str(SKILL_DIR))

from orchestrator import (  # noqa: E402
    ChemicalReviewOrchestrator,
    _document,
    _split_frontmatter,
)
from review import (  # noqa: E402
    IntegrityFinding,
    JournalAdaptation,
    JournalRequirement,
    ReviewAssessment,
)


class ReviewDeliveryTests(unittest.TestCase):
    def test_fixtures_cover_review_and_delivery_paths(self):
        fixture_dir = ROOT / "tests" / "fixtures" / "chemical-review"
        required = {
            "review-synchronized-delivery.md": ("single content source", "synchronized"),
            "review-claim-status.md": ("SOURCE_FACT", "MODEL_HYPOTHESIS"),
            "review-value-failure.md": ("summary", "revision"),
            "review-integrity-hard-stop.md": ("hard stop", "INTEGRITY_HOLD"),
            "review-nonblocking-uncertainty.md": ("uncertainty", "non-blocking"),
            "review-journal-adaptation.md": ("official", "journal"),
        }
        for filename, terms in required.items():
            text = (fixture_dir / filename).read_text(encoding="utf-8")
            for term in terms:
                self.assertIn(term, text)

    def test_single_content_source_generates_synchronized_clean_and_researcher_views(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)

            result = orchestrator.run_review(
                self._assessment(),
                self._journal_adaptation(),
            )

            self.assertEqual(result.phase, "REVIEW")
            self.assertEqual(result.status, "CANDIDATE_READY")
            clean_path = Path(project_dir, "clean-manuscript.md")
            researcher_path = Path(project_dir, "researcher-review.md")
            clean = clean_path.read_text(encoding="utf-8")
            researcher = researcher_path.read_text(encoding="utf-8")
            for text in (
                "Paper 1 reports a ligand-dependent pathway.",
                "The selected evidence supports condition-dependent mechanistic branches.",
                "A resting-state switch may control radical branching.",
            ):
                self.assertIn(text, clean)
                self.assertIn(text, researcher)
            for internal_label in ("SOURCE_FACT", "MODEL_SYNTHESIS", "MODEL_HYPOTHESIS"):
                self.assertNotIn(internal_label, clean)
                self.assertIn(internal_label, researcher)
            clean_meta, _ = _split_frontmatter(clean)
            researcher_meta, _ = _split_frontmatter(researcher)
            self.assertEqual(clean_meta["source_digest"], researcher_meta["source_digest"])
            self.assertEqual(clean_meta["source_content_revision"], "2")
            package = Path(project_dir, "submission-candidate-package.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("SUBMISSION_CANDIDATE", package)
            self.assertIn("does not claim scientific validity or journal acceptance", package)

    def test_fluent_summary_without_synthesis_value_requires_revision(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(
                project_dir,
                blocks=(
                    self._block(
                        section="Background",
                        claim_level="SOURCE_FACT",
                        contribution_type="comparison",
                        text="Paper 1 reports a ligand-dependent pathway.",
                        evidence_ids="paper-1",
                    ),
                ),
            )

            result = orchestrator.run_review(
                self._assessment(
                    value_status="SUMMARY_ONLY",
                    value_notes=(
                        "The comparison label does not change that this block only restates one source.",
                    ),
                ),
                self._journal_adaptation(),
            )

            self.assertEqual(result.status, "READY_FOR_NEXT_PHASE")
            report = Path(project_dir, "review-report.md").read_text(encoding="utf-8")
            self.assertIn("SUMMARY_ONLY", report)
            self.assertIn("comparison, explanation, rebuttal, trend, or a new hypothesis", report)
            package = Path(project_dir, "submission-candidate-package.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("REVISION_REQUIRED", package)

    def test_partial_output_write_is_rolled_back(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)
            original_write_text = Path.write_text

            def fail_after_partial_write(path, text, *args, **kwargs):
                if path.name == "researcher-review.md":
                    original_write_text(path, "partial", *args, **kwargs)
                    raise OSError("simulated delivery write failure")
                return original_write_text(path, text, *args, **kwargs)

            with patch.object(Path, "write_text", new=fail_after_partial_write):
                with self.assertRaisesRegex(OSError, "delivery write failure"):
                    orchestrator.run_review(
                        self._assessment(),
                        self._journal_adaptation(),
                    )

            for name in (
                "clean-manuscript.md",
                "researcher-review.md",
                "review-report.md",
                "submission-candidate-package.md",
            ):
                self.assertFalse(Path(project_dir, name).exists())

    def test_state_update_failure_rolls_back_delivery_outputs(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)
            state_path = Path(project_dir, "workflow-state.md")
            original_state = state_path.read_text(encoding="utf-8")
            original_write = orchestrator._write
            state_write_attempts = 0

            def fail_first_state_write(path, content):
                nonlocal state_write_attempts
                if path == state_path and state_write_attempts == 0:
                    state_write_attempts += 1
                    path.write_text("partial state", encoding="utf-8")
                    raise OSError("simulated state write failure")
                return original_write(path, content)

            with patch.object(orchestrator, "_write", new=fail_first_state_write):
                with self.assertRaisesRegex(OSError, "state write failure"):
                    orchestrator.run_review(
                        self._assessment(),
                        self._journal_adaptation(),
                    )

            self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)
            self.assertEqual(state_write_attempts, 1)
            for name in (
                "clean-manuscript.md",
                "researcher-review.md",
                "review-report.md",
                "submission-candidate-package.md",
            ):
                self.assertFalse(Path(project_dir, name).exists())

    def test_unstructured_content_outside_merge_blocks_fails_closed(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)
            content_path = Path(project_dir, "review-content.md")
            content = content_path.read_text(encoding="utf-8")
            content_path.write_text(
                content.replace(
                    "## Content blocks\n",
                    "## Content blocks\nUnstructured claim with no merge metadata.\n\n",
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "outside structured merge blocks"):
                orchestrator.run_review(
                    self._assessment(),
                    self._journal_adaptation(),
                )

    def test_narrow_integrity_finding_hard_stops_candidate_status(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)
            assessment = self._assessment(
                integrity_findings=(
                    IntegrityFinding(
                        kind="MISQUOTED_SOURCE_DATA",
                        detail="The draft reverses the reported selectivity trend.",
                        content_locator="Mechanistic comparison block 1",
                        source_locator="paper-1, Results section",
                    ),
                )
            )

            result = orchestrator.run_review(assessment, self._journal_adaptation())

            self.assertEqual(result.status, "WAITING_FOR_HUMAN")
            self.assertEqual(result.human_action, "REQUIRED")
            report = Path(project_dir, "review-report.md").read_text(encoding="utf-8")
            self.assertIn("MISQUOTED_SOURCE_DATA", report)
            self.assertIn("HARD_STOP", report)
            package = Path(project_dir, "submission-candidate-package.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("INTEGRITY_HOLD", package)
            clean_meta, _ = _split_frontmatter(
                Path(project_dir, "clean-manuscript.md").read_text(encoding="utf-8")
            )
            self.assertEqual(clean_meta["delivery_status"], "INTEGRITY_HOLD")

    def test_ordinary_uncertainty_is_actionable_but_not_a_total_stop(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)
            assessment = self._assessment(
                nonblocking_uncertainties=(
                    "Operando catalyst speciation remains incomplete for one ligand family.",
                )
            )

            result = orchestrator.run_review(assessment, self._journal_adaptation())

            self.assertEqual(result.status, "CANDIDATE_READY")
            report = Path(project_dir, "review-report.md").read_text(encoding="utf-8")
            self.assertIn("NON_BLOCKING", report)
            self.assertIn("Operando catalyst speciation", report)
            self.assertNotIn("INTEGRITY_HOLD", report)

    def test_journal_gap_is_recorded_as_revision_not_acceptance_prediction(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)
            journal = JournalAdaptation(
                target_journal="Example Chemistry",
                requirements=(
                    JournalRequirement(
                        requirement="Graphical abstract",
                        status="GAP",
                        note="A graphical abstract has not yet been prepared.",
                        source_locator="https://example.org/official-author-guide",
                    ),
                ),
            )

            result = orchestrator.run_review(self._assessment(), journal)

            self.assertEqual(result.status, "READY_FOR_NEXT_PHASE")
            report = Path(project_dir, "review-report.md").read_text(encoding="utf-8")
            self.assertIn("Graphical abstract", report)
            self.assertIn("GAP", report)
            self.assertIn("official-author-guide", report)
            package = Path(project_dir, "submission-candidate-package.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("REVISION_REQUIRED", package)
            self.assertIn("not a prediction of journal acceptance", package)

    def _review_ready_project(self, project_dir, *, blocks=None):
        root = Path(project_dir)
        root.joinpath("review-intent.md").write_text(
            _document(
                {
                    "kind": "review-intent",
                    "schema": "1",
                    "intent_revision": "0",
                    "confirmation": "CONFIRMED",
                },
                "# Review Intent\n\n"
                "## Research question\nHow do ligand and substrate contexts alter nickel pathways?\n\n"
                "## Core-claim candidates\nMechanistic branches are condition-dependent.\n\n"
                "## Scope and exclusions\nNickel C-C coupling; exclude palladium-only systems.\n\n"
                "## Audience or target journal\nExample Chemistry\n\n"
                "## Expected contribution\nReconcile apparently conflicting mechanisms.\n",
            ),
            encoding="utf-8",
        )
        root.joinpath("domain-profile.md").write_text(
            _document(
                {"kind": "domain-profile", "schema": "1"},
                "# Project Domain Profile\n\n"
                "## Chemical subfield\nOrganometallic chemistry\n",
            ),
            encoding="utf-8",
        )
        root.joinpath("workflow-state.md").write_text(
            _document(
                {
                    "kind": "chemical-review-workflow-state",
                    "schema": "1",
                    "phase": "IMPLEMENT",
                    "status": "READY_FOR_NEXT_PHASE",
                    "next_action": "Review the single content source.",
                    "intent_revision": "0",
                    "intent_confirmation": "CONFIRMED",
                    "human_action": "NONE",
                    "content_revision": "2",
                    "updated": "2026-08-23",
                },
                "# Workflow State\n\n"
                "## Current goal\nReview the merged content.\n\n"
                "## Recently completed\nMerged all units.\n\n"
                "## Open questions and risks\nNone recorded.\n\n"
                "## Tool degradation or HUMAN_ACTION_REQUIRED\nNone recorded.\n\n"
                "## Resume note\nReview is ready.\n",
            ),
            encoding="utf-8",
        )
        root.joinpath("review-blueprint.md").write_text(
            _document(
                {
                    "kind": "review-blueprint",
                    "schema": "1",
                    "blueprint_revision": "0",
                    "blueprint_status": "ADAPTABLE",
                    "frozen": "false",
                    "updated": "2026-08-23",
                },
                "# Review Blueprint\n\n"
                "## Narrative line\nFrom disagreement to condition-dependent branches.\n\n"
                "## Target-journal requirements\nUse the current official author guide.\n",
            ),
            encoding="utf-8",
        )
        if blocks is None:
            blocks = (
                self._block(
                    section="Background",
                    claim_level="SOURCE_FACT",
                    contribution_type="comparison",
                    text="Paper 1 reports a ligand-dependent pathway.",
                    evidence_ids="paper-1",
                ),
                self._block(
                    section="Mechanistic comparison",
                    claim_level="MODEL_SYNTHESIS",
                    contribution_type="explanation",
                    text="The selected evidence supports condition-dependent mechanistic branches.",
                    evidence_ids="paper-1, paper-2",
                ),
                self._block(
                    section="Research agenda",
                    claim_level="MODEL_HYPOTHESIS",
                    contribution_type="hypothesis",
                    text="A resting-state switch may control radical branching.",
                    evidence_ids="paper-1, paper-2",
                ),
            )
        root.joinpath("review-content.md").write_text(
            _document(
                {
                    "kind": "single-review-content-source",
                    "schema": "1",
                    "content_revision": "2",
                    "status": "ACTIVE",
                    "updated": "2026-08-23",
                },
                "# Review Content Source\n\n"
                "## Content blocks\n"
                + "\n\n".join(blocks)
                + "\n\n## Merge history\nAll fixture units merged.\n\n"
                "## Preserved human edits and conflicts\n\n"
                "## Human notes\n",
            ),
            encoding="utf-8",
        )
        return ChemicalReviewOrchestrator(project_dir)

    def _block(
        self,
        *,
        section,
        claim_level,
        contribution_type,
        text,
        evidence_ids,
    ):
        return (
            "### Merge 2 · Block\n"
            f"Section: {section}\n"
            f"Claim level: {claim_level}\n"
            f"Contribution type: {contribution_type}\n"
            "Source units: fixture-unit\n"
            f"Evidence IDs: {evidence_ids}\n"
            f"Text:\n{text}"
        )

    def _assessment(self, **overrides):
        values = {
            "value_status": "VALUE_PRODUCING",
            "value_notes": (
                "The review compares sources and develops a testable mechanistic explanation.",
            ),
            "chemical_reasoning_notes": (
                "Mechanistic explanations are framed as condition-dependent and testable.",
            ),
            "intent_alignment_notes": (
                "The narrative remains aligned with the confirmed nickel-coupling question.",
            ),
            "revision_requests": (),
            "nonblocking_uncertainties": (),
            "integrity_findings": (),
        }
        values.update(overrides)
        return ReviewAssessment(**values)

    def _journal_adaptation(self):
        return JournalAdaptation(
            target_journal="Example Chemistry",
            requirements=(
                JournalRequirement(
                    requirement="Narrative review structure",
                    status="MET",
                    note="Current section structure matches the review format.",
                    source_locator="https://example.org/official-author-guide",
                ),
            ),
        )


if __name__ == "__main__":
    unittest.main()
