from pathlib import Path
import hashlib
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
from delivery import (  # noqa: E402
    FigureAsset,
    FigureInventory,
    JournalProfile,
)
from review import (  # noqa: E402
    IntegrityFinding,
    JournalAdaptation,
    JournalGuideSnapshot,
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
            self.assertIn("research-evidence.md", package)
            self.assertIn("units/fixture-unit.md", package)

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
                guide=JournalGuideSnapshot(
                    target_journal="Example Chemistry",
                    source_locator="https://example.org/official-author-guide",
                    content="Review format and graphical abstract requirements.",
                    retrieved_at="2026-08-23",
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

    def test_candidate_package_requires_research_and_plan_assets(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)
            Path(project_dir, "research-evidence.md").unlink()

            with self.assertRaisesRegex(FileNotFoundError, "research-evidence.md"):
                orchestrator.run_review(self._assessment(), self._journal_adaptation())

    def test_candidate_package_requires_research_writing_unit_kind(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)
            Path(project_dir, "units", "fixture-unit.md").write_text(
                _document(
                    {"kind": "wrong-unit-kind", "schema": "1", "status": "MERGED"},
                    "# Research/Writing Unit: fixture-unit\n",
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError, r"fixture-unit\.md.*research-writing-unit"
            ):
                orchestrator.run_review(self._assessment(), self._journal_adaptation())

    def test_candidate_package_requires_delivery_evidence_and_nonempty_figure_inventory(self):
        required = (
            "source-registry.md",
            "coverage-matrix.md",
            "figure-inventory.md",
            "generic-chemistry-draft.docx.manifest.md",
        )
        for name in required:
            with self.subTest(missing=name), TemporaryDirectory() as project_dir:
                orchestrator = self._review_ready_project(project_dir)
                Path(project_dir, name).unlink()
                # The source registry is currently only reached through the optional
                # figure path; remove that path too so the regression proves the
                # registry itself is a required candidate asset.
                if name == "source-registry.md":
                    Path(project_dir, "figure-inventory.md").unlink()

                with self.assertRaisesRegex(FileNotFoundError, name):
                    orchestrator.run_review(self._assessment(), self._journal_adaptation())

        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)
            Path(project_dir, "figure-inventory.md").write_text(
                "---\nkind: figure-inventory\nschema: 1\nasset_count: 0\n---\n\n"
                "# Figure/Scheme/Table Inventory\n\n## Assets\nNone recorded.\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "exists but contains no figure assets"):
                orchestrator.run_review(self._assessment(), self._journal_adaptation())

    def test_journal_adaptation_requires_persisted_profile(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)
            Path(project_dir, "journal-profile.md").unlink()

            with self.assertRaisesRegex(FileNotFoundError, "journal-profile.md"):
                orchestrator.run_review(self._assessment(), self._journal_adaptation())

    def test_journal_adaptation_requires_profile_matching_saved_guide(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)
            profile_path = Path(project_dir, "journal-profile.md")
            profile_path.write_text(
                profile_path.read_text(encoding="utf-8").replace(
                    "Target journal\nExample Chemistry", "Target journal\nOther Chemistry"
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "journal-profile.md"):
                orchestrator.run_review(self._assessment(), self._journal_adaptation())

    def test_empty_figure_inventory_is_valid_for_an_explicit_no_figure_project(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)
            registry_path = Path(project_dir, "source-registry.md")
            registry_path.write_text(
                registry_path.read_text(encoding="utf-8").replace("table-1 | none", "none | none"),
                encoding="utf-8",
            )
            Path(project_dir, "figure-inventory.md").write_text(
                "---\nkind: figure-inventory\nschema: 1\nasset_count: 0\n---\n\n"
                "# Figure/Scheme/Table Inventory\n\n## Assets\nNone recorded.\n",
                encoding="utf-8",
            )
            Path(project_dir, "generic-chemistry-draft.docx").unlink()
            Path(project_dir, "generic-chemistry-draft.docx.manifest.md").unlink()
            orchestrator.export_docx()

            result = orchestrator.run_review(self._assessment(), self._journal_adaptation())

            self.assertEqual(result.status, "CANDIDATE_READY")
            package = Path(project_dir, "submission-candidate-package.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("figure-inventory.md", package)

    def test_reader_only_delivery_does_not_require_journal_adaptation(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._review_ready_project(project_dir)
            intent_path = Path(project_dir, "review-intent.md")
            intent = intent_path.read_text(encoding="utf-8")
            intent_path.write_text(
                intent.replace("Example Chemistry", "Target reader: Chemistry researchers"),
                encoding="utf-8",
            )

            result = orchestrator.run_review(self._assessment(), None)

            self.assertEqual(result.status, "CANDIDATE_READY")
            report = Path(project_dir, "review-report.md").read_text(encoding="utf-8")
            self.assertIn("NOT_APPLICABLE", report)

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
        for filename, kind, body in (
            (
                "research-evidence.md",
                "research-evidence",
                "# Research Evidence Package\n\n## Search paths\n- synonyms\n",
            ),
            (
                "literature-set.md",
                "layered-literature-set",
                "# Layered Literature Set\n\n## Anchor/core\n"
                "- paper-1: Evidence one [readiness: CLAIM_READY]\n"
                "- paper-2: Evidence two [readiness: CLAIM_READY]\n",
            ),
            (
                "unit-plan.md",
                "research-writing-unit-plan",
                "# Research/Writing Unit Plan\n\n## Units\n- fixture-unit\n",
            ),
        ):
            root.joinpath(filename).write_text(
                _document({"kind": kind, "schema": "1", "updated": "2026-08-23"}, body),
                encoding="utf-8",
            )
        root.joinpath("units").mkdir()
        root.joinpath("units", "fixture-unit.md").write_text(
            _document(
                {"kind": "research-writing-unit", "schema": "1", "status": "MERGED"},
                "# Research/Writing Unit: fixture-unit\n",
            ),
            encoding="utf-8",
        )
        root.joinpath("journal-guide.md").write_text(
            _document(
                {
                    "kind": "journal-guide-snapshot",
                    "schema": "1",
                    "target_journal": "Example Chemistry",
                    "source_locator": "https://example.org/official-author-guide",
                    "retrieved_at": "2026-08-23",
                    "content_digest": hashlib.sha256(
                        b"Review format and graphical abstract requirements."
                    ).hexdigest(),
                },
                "# Official Journal Guide Snapshot\n\n"
                "## Guide content\nReview format and graphical abstract requirements.\n",
            ),
            encoding="utf-8",
        )
        JournalProfile.selected(
            target_journal="Example Chemistry",
            guide_locator="https://example.org/official-author-guide",
            guide_retrieved_at="2026-08-23",
            guide_digest=hashlib.sha256(
                b"Review format and graphical abstract requirements."
            ).hexdigest(),
            requirements=("Margins: 1 inch",),
        ).persist(root)
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
                    "readiness": "CLAIM_READY",
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
        root.joinpath("source-registry.md").write_text(
            _document(
                {"kind": "research-source-registry", "schema": "1"},
                "# Source Registry\n\n"
                "| Source ID | Identity | Access basis | Full text | Parser | Media IDs | Digest |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| paper-1 | paper-1 | OPEN_ACCESS | FOUND | PARSED | table-1 | none |\n"
                "| paper-2 | paper-2 | OPEN_ACCESS | FOUND | PARSED | none | none |\n",
            ),
            encoding="utf-8",
        )
        root.joinpath("coverage-matrix.md").write_text(
            _document(
                {"kind": "research-coverage-matrix", "schema": "1"},
                "# Coverage Matrix\n\nCoverage recorded for the selected evidence.\n",
            ),
            encoding="utf-8",
        )
        inventory = FigureInventory(root)
        inventory.register_source_asset(
            FigureAsset(
                asset_id="table-1",
                asset_type="TABLE",
                source_id="paper-1",
                source_path="",
                locator="p. 1, Table 1",
                caption="Reported conditions.",
                provenance="Transcribed from the cited paper.",
                table_rows=(("Entry", "Yield"), ("A", "84%")),
                target_section="Background",
                target_paragraph="P-1",
                claim_ids=("Merge 2 · Block",),
                citation_ids=("paper-1",),
                extraction_status="VERIFIED",
            )
        )
        inventory.persist()
        orchestrator = ChemicalReviewOrchestrator(project_dir)
        orchestrator.export_docx()
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
            guide=JournalGuideSnapshot(
                target_journal="Example Chemistry",
                source_locator="https://example.org/official-author-guide",
                content="Review format and graphical abstract requirements.",
                retrieved_at="2026-08-23",
            ),
        )


if __name__ == "__main__":
    unittest.main()
