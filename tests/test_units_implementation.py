from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "chemical-review"
sys.path.insert(0, str(SKILL_DIR))

from orchestrator import ChemicalReviewOrchestrator  # noqa: E402
from prototype import BlueprintProposal, PrototypeSignal, PrototypeSubmission  # noqa: E402
from research import PaperRecord, ResearchConfig  # noqa: E402
from units import (  # noqa: E402
    ClaimBlock,
    MergeResolution,
    ResearchWritingUnit,
    UnitManager,
    UnitResult,
)


class DiscoveryFixture:
    name = "OpenAlex"

    def search(self, query, path):
        return [
            PaperRecord(
                "paper-1",
                "Ligand effects in nickel cross-coupling",
                keywords=("nickel", "ligand", "mechanism"),
                layer="anchor/core",
                source=self.name,
            ),
            PaperRecord(
                "paper-2",
                "Competing radical pathways",
                keywords=("radical", "counterevidence"),
                layer="controversy",
                source=self.name,
            ),
        ]


class UnitImplementationTests(unittest.TestCase):
    def test_fixtures_cover_issue_and_implement_paths(self):
        fixture_dir = ROOT / "tests" / "fixtures" / "chemical-review"
        required = {
            "unit-dependency-blocking.md": ("prerequisite", "not ready"),
            "unit-parallel-results.md": ("independent", "own research asset"),
            "unit-merge-conflict.md": ("conflict", "central merge"),
            "unit-section-drafting.md": ("MODEL_SYNTHESIS", "section"),
            "unit-human-edit-preservation.md": ("human edit", "preserved"),
        }
        for filename, terms in required.items():
            text = (fixture_dir / filename).read_text(encoding="utf-8")
            for term in terms:
                self.assertIn(term, text)

    def test_dependency_blocking_and_ready_units(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                (
                    self._unit("term-check"),
                    self._unit("paper-comparison", prerequisites=("term-check",)),
                    self._unit("mechanism-draft", prerequisites=("paper-comparison",)),
                ),
            )

            self.assertEqual(orchestrator.ready_review_units(), ("term-check",))
            with self.assertRaisesRegex(ValueError, "not ready"):
                orchestrator.submit_review_unit_result(
                    self._result("paper-comparison", section="Mechanistic comparison")
                )

            orchestrator.submit_review_unit_result(self._result("term-check"))
            self.assertEqual(orchestrator.ready_review_units(), ("paper-comparison",))

    def test_stale_or_human_edited_ready_status_cannot_bypass_prerequisite(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                (
                    self._unit("term-check"),
                    self._unit("paper-comparison", prerequisites=("term-check",)),
                ),
            )
            dependent_path = Path(project_dir, "units", "paper-comparison.md")
            dependent_path.write_text(
                dependent_path.read_text(encoding="utf-8").replace(
                    "status: PENDING", "status: READY"
                ),
                encoding="utf-8",
            )

            self.assertEqual(orchestrator.ready_review_units(), ("term-check",))
            with self.assertRaisesRegex(ValueError, "prerequisites.*incomplete"):
                orchestrator.submit_review_unit_result(self._result("paper-comparison"))

    def test_independent_results_can_arrive_in_any_order_and_stay_isolated(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                (
                    self._unit("term-check"),
                    self._unit("controversy-scan"),
                    self._unit(
                        "mechanism-draft",
                        prerequisites=("term-check", "controversy-scan"),
                    ),
                ),
            )
            self.assertEqual(
                set(orchestrator.ready_review_units()),
                {"term-check", "controversy-scan"},
            )

            orchestrator.submit_review_unit_result(self._result("controversy-scan"))
            orchestrator.submit_review_unit_result(self._result("term-check"))

            self.assertTrue(Path(project_dir, "units", "term-check.md").exists())
            self.assertTrue(Path(project_dir, "units", "controversy-scan.md").exists())
            self.assertFalse(Path(project_dir, "review-content.md").exists())
            self.assertEqual(orchestrator.ready_review_units(), ("mechanism-draft",))

            resumed = ChemicalReviewOrchestrator(project_dir)
            self.assertEqual(resumed.ready_review_units(), ("mechanism-draft",))

    def test_conflicting_parallel_results_require_visible_central_resolution(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                (self._unit("anchor-analysis"), self._unit("counter-analysis")),
            )
            orchestrator.submit_review_unit_result(
                self._result(
                    "anchor-analysis",
                    section="Mechanistic comparison",
                    text="The anchor evidence supports a closed-shell branch.",
                    evidence_ids=("paper-1",),
                )
            )
            orchestrator.submit_review_unit_result(
                self._result(
                    "counter-analysis",
                    section="Mechanistic comparison",
                    text="The counterevidence supports radical branching under a subset of conditions.",
                    evidence_ids=("paper-2",),
                )
            )

            conflicted = orchestrator.merge_review_units(
                ("anchor-analysis", "counter-analysis"),
                conflict_sections=("Mechanistic comparison",),
            )
            self.assertEqual(conflicted.status, "WAITING_FOR_HUMAN")
            self.assertEqual(conflicted.human_action, "REQUIRED")
            merge_review = Path(project_dir, "merge-review.md").read_text(encoding="utf-8")
            self.assertIn("Mechanistic comparison", merge_review)
            self.assertIn("anchor-analysis", merge_review)
            self.assertIn("counter-analysis", merge_review)
            self.assertFalse(Path(project_dir, "review-content.md").exists())
            merge_review_path = Path(project_dir, "merge-review.md")
            merge_review_path.write_text(
                merge_review.replace(
                    "The anchor evidence supports a closed-shell branch.",
                    "HUMAN EDIT: retain the closed-shell boundary as a candidate.",
                ),
                encoding="utf-8",
            )

            resolved = orchestrator.merge_review_units(
                ("anchor-analysis", "counter-analysis"),
                conflict_sections=("Mechanistic comparison",),
                resolutions=(
                    MergeResolution(
                        section="Mechanistic comparison",
                        text=(
                            "The selected evidence supports condition-dependent closed-shell and "
                            "radical branches rather than one universal mechanism."
                        ),
                        claim_level="MODEL_SYNTHESIS",
                        contribution_type="explanation",
                        evidence_ids=("paper-1", "paper-2"),
                        rationale="Retain both findings and make their condition boundary explicit.",
                    ),
                ),
            )
            self.assertEqual(resolved.status, "READY_FOR_NEXT_PHASE")
            content = Path(project_dir, "review-content.md").read_text(encoding="utf-8")
            self.assertIn("MODEL_SYNTHESIS", content)
            self.assertIn("condition-dependent", content)
            self.assertIn("anchor-analysis, counter-analysis", content)
            resolved_review = merge_review_path.read_text(encoding="utf-8")
            self.assertIn("Preserved human edits and conflicts", resolved_review)
            self.assertIn(
                "HUMAN EDIT: retain the closed-shell boundary as a candidate.",
                resolved_review,
            )

    def test_compatible_claims_for_one_section_do_not_conflict_by_default(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                (self._unit("conditions"), self._unit("evidence-quality")),
            )
            orchestrator.submit_review_unit_result(
                self._result(
                    "conditions",
                    section="Mechanistic comparison",
                    text="Ligand and substrate context should be compared explicitly.",
                )
            )
            orchestrator.submit_review_unit_result(
                self._result(
                    "evidence-quality",
                    section="Mechanistic comparison",
                    text="Mechanistic probes have different inferential limits.",
                    evidence_ids=("paper-2",),
                )
            )

            merged = orchestrator.merge_review_units(("conditions", "evidence-quality"))

            self.assertEqual(merged.status, "READY_FOR_NEXT_PHASE")
            content = Path(project_dir, "review-content.md").read_text(encoding="utf-8")
            self.assertIn("Ligand and substrate context", content)
            self.assertIn("different inferential limits", content)

    def test_merge_retry_after_status_write_failure_is_idempotent(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                (self._unit("mechanism-draft"), self._unit("evidence-draft")),
            )
            result_text = "A bounded mechanism explanation from one completed unit."
            second_text = "A bounded evidence-quality note from another completed unit."
            orchestrator.submit_review_unit_result(
                self._result("mechanism-draft", text=result_text)
            )
            orchestrator.submit_review_unit_result(
                self._result("evidence-draft", text=second_text, evidence_ids=("paper-2",))
            )
            original_update = UnitManager._update_unit_metadata
            failed_once = False

            def fail_first_status_write(manager, unit_id, updates):
                nonlocal failed_once
                if updates.get("status") == "MERGED" and not failed_once:
                    failed_once = True
                    raise OSError("injected unit-status failure")
                return original_update(manager, unit_id, updates)

            with patch.object(UnitManager, "_update_unit_metadata", fail_first_status_write):
                with self.assertRaisesRegex(OSError, "injected unit-status failure"):
                    orchestrator.merge_review_units(("mechanism-draft", "evidence-draft"))

            first_content = Path(project_dir, "review-content.md").read_text(encoding="utf-8")
            self.assertEqual(first_content.count(result_text), 1)
            self.assertEqual(first_content.count(second_text), 1)

            recovered_first = orchestrator.merge_review_units(("evidence-draft",))
            self.assertEqual(recovered_first.status, "ACTIVE")
            recovered = orchestrator.merge_review_units(("mechanism-draft",))

            self.assertEqual(recovered.status, "READY_FOR_NEXT_PHASE")
            final_content = Path(project_dir, "review-content.md").read_text(encoding="utf-8")
            self.assertEqual(final_content.count(result_text), 1)
            self.assertEqual(final_content.count(second_text), 1)
            self.assertEqual(final_content.count("### Merge 0"), 3)  # two blocks and one history entry

    def test_result_submission_rejects_unit_asset_not_declared_by_plan(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                (self._unit("declared-unit"),),
            )
            declared_path = Path(project_dir, "units", "declared-unit.md")
            rogue_path = Path(project_dir, "units", "rogue-unit.md")
            rogue_path.write_text(
                declared_path.read_text(encoding="utf-8").replace(
                    "declared-unit", "rogue-unit"
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "not declared"):
                orchestrator.submit_review_unit_result(self._result("rogue-unit"))

    def test_human_edited_merge_history_cannot_forge_recovery(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                (self._unit("first-unit"), self._unit("second-unit")),
            )
            first_text = "First unit content was genuinely merged."
            second_text = "Second unit content has not been merged yet."
            orchestrator.submit_review_unit_result(
                self._result("first-unit", text=first_text)
            )
            orchestrator.submit_review_unit_result(
                self._result("second-unit", text=second_text, evidence_ids=("paper-2",))
            )
            orchestrator.merge_review_units(("first-unit",))
            content_path = Path(project_dir, "review-content.md")
            content_path.write_text(
                content_path.read_text(encoding="utf-8").replace(
                    "Accepted units: first-unit",
                    "Accepted units: first-unit, second-unit",
                ),
                encoding="utf-8",
            )

            held = orchestrator.merge_review_units(("second-unit",))

            self.assertEqual(held.status, "WAITING_FOR_HUMAN")
            self.assertEqual(held.human_action, "REQUIRED")
            content = content_path.read_text(encoding="utf-8")
            self.assertIn("Direct human edit detected in Merge history", content)
            self.assertNotIn(second_text, content)
            second_unit = Path(project_dir, "units", "second-unit.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("status: COMPLETE", second_unit)

    def test_unit_plan_creation_failure_rolls_back_owned_partial_assets(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._prd_project(project_dir)
            orchestrator.accept_review_blueprint()
            manager = UnitManager(project_dir)
            first = self._unit("first-unit")
            second = self._unit("second-unit")
            original_write = manager._write_unit

            def fail_second_write(unit, *, status):
                if unit.unit_id == "second-unit":
                    raise OSError("injected plan write failure")
                return original_write(unit, status=status)

            with patch.object(manager, "_write_unit", side_effect=fail_second_write):
                with self.assertRaisesRegex(OSError, "injected plan write failure"):
                    manager.create_plan((first, second))

            self.assertFalse(Path(project_dir, "unit-plan.md").exists())
            self.assertFalse(Path(project_dir, "units").exists())

    def test_claim_evidence_ids_must_exist_in_saved_research_assets(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                (self._unit("source-check"),),
            )

            with self.assertRaisesRegex(ValueError, "absent from Research"):
                orchestrator.submit_review_unit_result(
                    self._result("source-check", evidence_ids=("invented-paper",))
                )

    def test_section_draft_retains_claim_levels_and_synthesis_modes(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                (self._unit("section-draft", kind="section_claim"),),
            )
            orchestrator.submit_review_unit_result(
                UnitResult(
                    unit_id="section-draft",
                    completion_evidence="Drafted three claim types from the selected evidence.",
                    findings=("The reports diverge across ligand and substrate regimes.",),
                    claims=(
                        ClaimBlock(
                            section="Mechanistic comparison",
                            claim_level="SOURCE_FACT",
                            contribution_type="comparison",
                            text="The selected studies report different favored pathways.",
                            evidence_ids=("paper-1", "paper-2"),
                            comparability_status="COMPARABLE",
                            comparability_basis="Compared ligand, substrate, units, and reported endpoints.",
                        ),
                        ClaimBlock(
                            section="Mechanistic comparison",
                            claim_level="MODEL_SYNTHESIS",
                            contribution_type="rebuttal",
                            text="The evidence does not support a context-free universal pathway.",
                            evidence_ids=("paper-1", "paper-2"),
                            comparability_status="COMPARABLE",
                            comparability_basis="Compared ligand, substrate, units, and reported endpoints.",
                        ),
                        ClaimBlock(
                            section="Research agenda",
                            claim_level="MODEL_HYPOTHESIS",
                            contribution_type="hypothesis",
                            text="A ligand-dependent resting-state switch may determine branching.",
                            evidence_ids=("paper-1", "paper-2"),
                            comparability_status="COMPARABLE",
                            comparability_basis="Compared ligand, substrate, units, and reported endpoints.",
                        ),
                    ),
                    remaining_uncertainty="Operando speciation is not yet available.",
                )
            )
            orchestrator.merge_review_units(("section-draft",))

            content = Path(project_dir, "review-content.md").read_text(encoding="utf-8")
            for term in (
                "SOURCE_FACT",
                "MODEL_SYNTHESIS",
                "MODEL_HYPOTHESIS",
                "comparison",
                "rebuttal",
                "hypothesis",
            ):
                self.assertIn(term, content)

    def test_legacy_literature_without_inline_readiness_keeps_evidence_compatibility(self):
        """Old literature-set entries remain evidence-ready until explicitly downgraded."""
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                (self._unit("legacy-source-fact", kind="section_claim"),),
            )

            submitted = orchestrator.submit_review_unit_result(
                UnitResult(
                    unit_id="legacy-source-fact",
                    completion_evidence="A legacy fixture supplied a source-backed claim.",
                    findings=("The selected legacy fixture reports the bounded finding.",),
                    claims=(
                        ClaimBlock(
                            section="Evidence notes",
                            claim_level="SOURCE_FACT",
                            contribution_type="explanation",
                            text="The selected study reports the bounded finding.",
                            evidence_ids=("paper-1",),
                        ),
                    ),
                    remaining_uncertainty="The legacy fixture does not record per-source readiness.",
                )
            )
            self.assertEqual(submitted.status, "READY_FOR_NEXT_PHASE")

    def test_later_merge_preserves_and_surfaces_direct_human_content_edit(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                (self._unit("first-draft"), self._unit("second-draft")),
            )
            orchestrator.submit_review_unit_result(
                self._result("first-draft", section="Background", text="Initial background draft.")
            )
            orchestrator.merge_review_units(("first-draft",))
            content_path = Path(project_dir, "review-content.md")
            content_path.write_text(
                content_path.read_text(encoding="utf-8").replace(
                    "Initial background draft.",
                    "HUMAN EDIT: retain the solvent-dependent boundary.",
                ),
                encoding="utf-8",
            )

            orchestrator.submit_review_unit_result(
                self._result(
                    "second-draft",
                    section="Research agenda",
                    text="Test the solvent-dependent boundary across ligand families.",
                )
            )
            orchestrator.merge_review_units(("second-draft",))

            content = content_path.read_text(encoding="utf-8")
            self.assertIn("HUMAN EDIT: retain the solvent-dependent boundary.", content)
            self.assertIn("Preserved human edits and conflicts", content)
            self.assertIn("Direct human edit detected", content)
            self.assertIn("Test the solvent-dependent boundary", content)

    def test_blocked_unit_requests_human_action_and_can_retry(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                (self._unit("full-text-check"),),
            )
            blocked = orchestrator.submit_review_unit_result(
                UnitResult(
                    unit_id="full-text-check",
                    completion_evidence="",
                    findings=(),
                    claims=(),
                    remaining_uncertainty="The experimental conditions remain unavailable.",
                    tool_degradation="Authorized full text is unavailable.",
                    human_action_required="Provide an authorized PDF or accept abstract-only degradation.",
                )
            )
            self.assertEqual(blocked.status, "WAITING_FOR_HUMAN")
            self.assertEqual(blocked.human_action, "REQUIRED")
            unit = Path(project_dir, "units", "full-text-check.md").read_text(encoding="utf-8")
            self.assertIn("status: BLOCKED", unit)
            self.assertIn("Authorized full text is unavailable", unit)

            retried = orchestrator.retry_review_unit("full-text-check")
            self.assertEqual(retried.status, "ACTIVE")
            completed = orchestrator.submit_review_unit_result(
                self._result("full-text-check", section="Evidence boundary")
            )
            self.assertEqual(completed.status, "READY_FOR_NEXT_PHASE")

    def _implementation_project(self, project_dir, units):
        orchestrator = self._prd_project(project_dir)
        entered = orchestrator.accept_review_blueprint()
        self.assertEqual(entered.phase, "ISSUES")
        planned = orchestrator.create_review_units(units)
        self.assertEqual(planned.status, "READY_FOR_NEXT_PHASE")
        implementing = orchestrator.accept_unit_plan()
        self.assertEqual(implementing.phase, "IMPLEMENT")
        return orchestrator

    def _prd_project(self, project_dir):
        orchestrator = ChemicalReviewOrchestrator(project_dir)
        orchestrator.start("nickel-catalyzed cross-coupling mechanisms")
        orchestrator.continue_grill(
            {
                "core_claims": "Mechanistic pathways depend on ligand and substrate context.",
                "scope": "Nickel-catalyzed C-C cross-coupling",
                "exclusions": "Palladium-only systems",
                "audience": "Organometallic chemistry researchers",
                "contribution": "Reconcile apparently conflicting mechanistic evidence",
            }
        )
        orchestrator.confirm_current_intent()
        orchestrator.run_research(ResearchConfig(discovery=(DiscoveryFixture(),)))
        orchestrator.accept_research_handoff()
        orchestrator.run_prototype(
            PrototypeSubmission(
                paper_ids=("paper-1", "paper-2"),
                representative_reason="The pair spans an anchor claim and counterevidence.",
                value_argument="A condition-centred comparison may reconcile the disagreement.",
                signals=(
                    PrototypeSignal(
                        kind="comparison",
                        statement="Compare ligand, substrate, and mechanistic probes.",
                        evidence_ids=("paper-1", "paper-2"),
                        value_gain="Tests whether the apparent contradiction is condition-dependent.",
                    ),
                ),
                risks=("Operando evidence remains sparse.",),
            )
        )
        orchestrator.accept_prototype_handoff()
        orchestrator.build_review_blueprint(
            BlueprintProposal(
                section_structure=("Background", "Mechanistic comparison", "Research agenda"),
                narrative_line="Move from apparent contradiction to condition-dependent branches.",
                comparison_dimensions=("ligand class", "substrate class", "mechanistic probe"),
                evidence_strategy=("Anchor evidence", "Counterevidence", "Full-text verification"),
                target_journal_requirements=("Target journal remains to be confirmed.",),
                known_risks=("Uneven catalyst-speciation reporting.",),
                candidate_units=("Verify terms", "Compare papers", "Draft mechanism section"),
            )
        )
        return orchestrator

    def _unit(self, unit_id, *, kind="paper_comparison", prerequisites=()):
        return ResearchWritingUnit(
            unit_id=unit_id,
            kind=kind,
            purpose=f"Resolve {unit_id} for the review argument.",
            prerequisites=prerequisites,
            completion_signal=f"A checkable result exists for {unit_id}.",
            remaining_uncertainty="Broader evidence may revise the result.",
        )

    def _result(
        self,
        unit_id,
        *,
        section="Evidence notes",
        text="The selected evidence supports a bounded finding.",
        evidence_ids=("paper-1",),
    ):
        return UnitResult(
            unit_id=unit_id,
            completion_evidence=f"Completed the declared signal for {unit_id}.",
            findings=(f"Finding from {unit_id}.",),
            claims=(
                ClaimBlock(
                    section=section,
                    claim_level="MODEL_SYNTHESIS",
                    contribution_type="explanation",
                    text=text,
                    evidence_ids=evidence_ids,
                ),
            ),
            remaining_uncertainty="The synthesis remains open to broader evidence.",
        )


if __name__ == "__main__":
    unittest.main()
