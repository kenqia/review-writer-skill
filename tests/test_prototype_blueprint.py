from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "chemical-review"
sys.path.insert(0, str(SKILL_DIR))

from orchestrator import ChemicalReviewOrchestrator  # noqa: E402
from prototype import BlueprintProposal, PrototypeRunner, PrototypeSignal, PrototypeSubmission  # noqa: E402
from research import PaperRecord, ResearchConfig  # noqa: E402


class DiscoveryFixture:
    name = "OpenAlex"

    def search(self, query, path):
        return [
            PaperRecord(
                "paper-1",
                "Ligand effects in nickel cross-coupling",
                authors=("A. Researcher",),
                keywords=("nickel", "ligand", "mechanism"),
                layer="anchor/core",
                source=self.name,
            ),
            PaperRecord(
                "paper-2",
                "Competing radical pathways",
                authors=("B. Researcher",),
                keywords=("radical", "counterevidence"),
                layer="controversy",
                source=self.name,
            ),
        ]


class PrototypeBlueprintTests(unittest.TestCase):
    def test_url_evidence_ids_preserve_colons_during_selection_validation(self):
        with TemporaryDirectory() as project_dir:
            doi_id = "https://doi.org/10.1000/example"
            url_id = "https://example.org/paper:1"
            Path(project_dir, "research-evidence.md").write_text(
                "---\nkind: research-evidence\n---\n# Research Evidence Package\n",
                encoding="utf-8",
            )
            Path(project_dir, "literature-set.md").write_text(
                "---\nkind: layered-literature-set\n---\n"
                "# Layered Literature Set\n\n"
                "## Anchor/core\n"
                f"- {doi_id}: DOI evidence\n"
                f"- {url_id}: URL evidence\n",
                encoding="utf-8",
            )

            selected = PrototypeRunner(project_dir)._validate_selection(
                PrototypeSubmission(
                    paper_ids=(doi_id, url_id),
                    representative_reason="These URL identities must remain complete.",
                )
            )

            self.assertEqual(selected, (doi_id, url_id))

    def test_fixtures_cover_summary_value_and_revision_paths(self):
        fixture_dir = ROOT / "tests" / "fixtures" / "chemical-review"
        required = {
            "prototype-summary-only.md": ("SUMMARY_ONLY", "Research handoff", "major risks"),
            "prototype-value-handoff.md": ("VALUE_PRODUCING", "PRD handoff", "new research question"),
            "blueprint-new-evidence-revision.md": ("blueprint_revision", "Revision history", "ADAPTABLE"),
        }
        for filename, terms in required.items():
            text = (fixture_dir / filename).read_text(encoding="utf-8")
            for term in terms:
                self.assertIn(term, text)

    def test_summary_only_prototype_routes_back_to_research(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._prototype_ready_project(project_dir)
            research_before = Path(project_dir, "research-evidence.md").read_text(encoding="utf-8")

            result = orchestrator.run_prototype(
                PrototypeSubmission(
                    paper_ids=("paper-1", "paper-2"),
                    representative_reason="Anchor and controversy candidates test the mechanism question.",
                    draft="Paper 1 reports one mechanism. Paper 2 reports another mechanism.",
                    risks=("Conditions have not yet been normalized.",),
                )
            )

            self.assertEqual(result.phase, "PROTOTYPE")
            self.assertEqual(result.assets["prototype_value_status"], "SUMMARY_ONLY")
            self.assertEqual(result.assets["prototype_handoff"], "RESEARCH")
            prototype = Path(project_dir, "prototype-result.md").read_text(encoding="utf-8")
            self.assertIn("Fluent summary is not sufficient", prototype)
            self.assertIn("Conditions have not yet been normalized", prototype)
            self.assertEqual(
                research_before,
                Path(project_dir, "research-evidence.md").read_text(encoding="utf-8"),
            )
            accepted = orchestrator.accept_prototype_handoff()
            self.assertEqual(accepted.phase, "RESEARCH")

    def test_value_producing_subsection_prototype_can_handoff_to_prd(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._prototype_ready_project(project_dir)
            result = orchestrator.run_prototype(
                PrototypeSubmission(
                    subsection="Ligand-controlled mechanistic divergence",
                    subsection_evidence_ids=("paper-1", "paper-2"),
                    representative_reason="One subsection tests whether conditions explain apparently conflicting pathways.",
                    draft="The same mechanistic label hides distinct kinetic regimes.",
                    value_argument="Reframing the disagreement by kinetic regime changes how experiments should be compared.",
                    signals=(
                        PrototypeSignal(
                            kind="comparison",
                            statement="Compare ligand class, substrate class, temperature, and radical-clock evidence.",
                            evidence_ids=("paper-1", "paper-2"),
                            value_gain="Exposes condition-dependent differences hidden by mechanism labels.",
                        ),
                        PrototypeSignal(
                            kind="explanation",
                            statement="Ligand-dependent resting states can reconcile the reported pathway difference.",
                            evidence_ids=("paper-1", "paper-2"),
                            value_gain="Offers a testable reconciliation instead of repeating both reports.",
                        ),
                        PrototypeSignal(
                            kind="rebuttal",
                            statement="A universal radical mechanism is not supported across both condition sets.",
                            evidence_ids=("paper-1", "paper-2"),
                            value_gain="Challenges an over-generalized interpretation and names its boundary.",
                        ),
                        PrototypeSignal(
                            kind="new_research_question",
                            statement="Which observable distinguishes catalyst-controlled from substrate-controlled branching?",
                            evidence_ids=("paper-1", "paper-2"),
                            value_gain="Turns the disagreement into a discriminating experiment question.",
                        ),
                    ),
                    risks=("The explanation remains a model synthesis pending broader full-text checks.",),
                )
            )

            self.assertEqual(result.assets["prototype_value_status"], "VALUE_PRODUCING")
            self.assertEqual(result.assets["prototype_handoff"], "PRD")
            prototype = Path(project_dir, "prototype-result.md").read_text(encoding="utf-8")
            for heading in ("Comparisons", "Explanations", "Rebuttals", "New research questions", "Major risks"):
                self.assertIn(f"## {heading}", prototype)
            handed_off = orchestrator.accept_prototype_handoff()
            self.assertEqual(handed_off.phase, "PRD")

    def test_prd_builds_adaptable_blueprint_and_revises_after_new_evidence(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._prototype_ready_project(project_dir)
            orchestrator.run_prototype(
                PrototypeSubmission(
                    paper_ids=("paper-1", "paper-2"),
                    representative_reason="The pair spans the anchor claim and its counterevidence.",
                    value_argument="The condition-centred comparison can reconcile an apparent mechanistic contradiction.",
                    signals=(
                        PrototypeSignal(
                            kind="comparison",
                            statement="Compare ligand, substrate, and mechanistic probe.",
                            evidence_ids=("paper-1", "paper-2"),
                            value_gain="Tests whether the apparent contradiction is condition-dependent.",
                        ),
                        PrototypeSignal(
                            kind="explanation",
                            statement="Different resting states may explain the disagreement.",
                            evidence_ids=("paper-1", "paper-2"),
                            value_gain="Provides a testable reconciliation of the selected evidence.",
                        ),
                    ),
                    risks=("Sparse operando evidence.",),
                )
            )
            orchestrator.accept_prototype_handoff()
            research_before = Path(project_dir, "research-evidence.md").read_text(encoding="utf-8")
            blueprint = orchestrator.build_review_blueprint(
                BlueprintProposal(
                    section_structure=(
                        "Problem and vocabulary",
                        "Mechanistic evidence by ligand family",
                        "Counterevidence and boundary conditions",
                        "Testable research agenda",
                    ),
                    narrative_line="Move from apparent contradiction to condition-dependent mechanistic branches.",
                    comparison_dimensions=("ligand class", "substrate class", "temperature", "mechanistic probe"),
                    evidence_strategy=("Anchor primary studies", "Counterevidence", "Authorized full-text verification"),
                    target_journal_requirements=("Journal not yet confirmed; retain adaptable length and figure plan.",),
                    known_risks=("Uneven reporting of catalyst speciation.",),
                    candidate_units=("Verify ligand terminology", "Build condition-comparability table", "Draft mechanism section"),
                )
            )
            self.assertEqual(blueprint.phase, "PRD")
            self.assertEqual(blueprint.assets["blueprint_status"], "ADAPTABLE")
            blueprint_path = Path(project_dir, "review-blueprint.md")
            first = blueprint_path.read_text(encoding="utf-8")
            for heading in (
                "Research question",
                "Core-claim candidates",
                "Section structure",
                "Narrative line",
                "Comparison dimensions",
                "Evidence strategy",
                "Expected contribution",
                "Target-journal requirements",
                "Known risks",
                "Candidate research/writing units",
            ):
                self.assertIn(f"## {heading}", first)
            self.assertIn("adaptive", first.lower())
            self.assertEqual(
                research_before,
                Path(project_dir, "research-evidence.md").read_text(encoding="utf-8"),
            )

            research_path = Path(project_dir, "research-evidence.md")
            research_path.write_text(
                research_path.read_text(encoding="utf-8").replace(
                    "## Human notes\n",
                    "## Human notes\n- New spectroscopy evidence indicates a catalyst-speciation branch.\n",
                ),
                encoding="utf-8",
            )
            research_with_new_evidence = research_path.read_text(encoding="utf-8")

            revised = orchestrator.revise_review_blueprint(
                {"comparison_dimensions": ("ligand class", "substrate class", "catalyst speciation")},
                evidence_note="New spectroscopy evidence makes catalyst speciation a first-class comparison axis.",
            )
            self.assertEqual(revised.assets["blueprint_revision"], "1")
            second = blueprint_path.read_text(encoding="utf-8")
            self.assertIn("catalyst speciation", second)
            self.assertIn("Revision history", second)
            self.assertIn("New spectroscopy evidence", second)
            self.assertEqual(
                research_with_new_evidence,
                Path(project_dir, "research-evidence.md").read_text(encoding="utf-8"),
            )
            resumed = ChemicalReviewOrchestrator(project_dir).resume()
            self.assertEqual(resumed.phase, "PRD")
            self.assertEqual(resumed.next_action, revised.next_action)

    def test_subsection_selection_requires_research_evidence_ids(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._prototype_ready_project(project_dir)

            with self.assertRaisesRegex(ValueError, "subsection.*evidence"):
                orchestrator.run_prototype(
                    PrototypeSubmission(
                        subsection="An invented subsection name",
                        representative_reason="Tests a proposed mechanistic boundary.",
                        risks=("The selected evidence boundary is not yet established.",),
                    )
                )

    def test_signal_must_bind_only_selected_research_evidence(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._prototype_ready_project(project_dir)

            with self.assertRaisesRegex(ValueError, "selected Research evidence"):
                orchestrator.run_prototype(
                    PrototypeSubmission(
                        paper_ids=("paper-1",),
                        representative_reason="Tests one anchor paper before broadening the sample.",
                        value_argument="The mechanism claim suggests a boundary worth testing.",
                        signals=(
                            PrototypeSignal(
                                kind="explanation",
                                statement="A ligand-dependent resting state could explain the reported trend.",
                                evidence_ids=("paper-2",),
                                value_gain="Forms a testable explanation instead of a summary.",
                            ),
                        ),
                        risks=("The explanation uses evidence outside the selected sample.",),
                    )
                )

            receipt = Path(project_dir, "workflow-failure-receipt.md")
            self.assertTrue(receipt.is_file())
            self.assertIn("status: BLOCKED", receipt.read_text(encoding="utf-8"))
            self.assertIn("PROTOTYPE", receipt.read_text(encoding="utf-8"))
            resumed = ChemicalReviewOrchestrator(project_dir).resume()
            self.assertEqual(resumed.status, "WAITING_FOR_HUMAN")
            self.assertEqual(resumed.human_action, "REQUIRED")
            self.assertIn("HUMAN_ACTION_REQUIRED", resumed.next_action)

    def test_blank_paper_id_is_not_a_research_selection(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._prototype_ready_project(project_dir)

            with self.assertRaisesRegex(ValueError, "non-empty Research evidence"):
                orchestrator.run_prototype(
                    PrototypeSubmission(
                        paper_ids=("",),
                        representative_reason="A blank identifier cannot select evidence.",
                        risks=("No evidence record was selected.",),
                    )
                )

    def test_comparison_signal_requires_two_selected_evidence_records(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._prototype_ready_project(project_dir)

            with self.assertRaisesRegex(ValueError, "comparison.*two"):
                orchestrator.run_prototype(
                    PrototypeSubmission(
                        paper_ids=("paper-1",),
                        representative_reason="Tests whether one anchor paper supports comparison.",
                        value_argument="A cross-condition comparison could add value.",
                        signals=(
                            PrototypeSignal(
                                kind="comparison",
                                statement="Compare ligand and temperature effects.",
                                evidence_ids=("paper-1",),
                                value_gain="Attempts to expose condition dependence.",
                            ),
                        ),
                        risks=("Only one selected evidence record is available.",),
                    )
                )

    def test_prototype_rerun_preserves_direct_human_edit_as_conflict_input(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._prototype_ready_project(project_dir)
            first_submission = PrototypeSubmission(
                paper_ids=("paper-1", "paper-2"),
                representative_reason="The pair spans the anchor claim and its counterevidence.",
                draft="Initial agent draft.",
                risks=("Conditions remain incompletely normalized.",),
            )
            orchestrator.run_prototype(first_submission)
            prototype_path = Path(project_dir, "prototype-result.md")
            prototype_path.write_text(
                prototype_path.read_text(encoding="utf-8").replace(
                    "Initial agent draft.",
                    "HUMAN EDIT: preserve the ligand-specific caveat.",
                ),
                encoding="utf-8",
            )

            orchestrator.run_prototype(
                PrototypeSubmission(
                    paper_ids=("paper-1", "paper-2"),
                    representative_reason="The same pair is rerun after checking conditions.",
                    draft="Revised agent draft.",
                    risks=("Full-text verification remains incomplete.",),
                )
            )

            prototype = prototype_path.read_text(encoding="utf-8")
            self.assertIn("HUMAN EDIT: preserve the ligand-specific caveat.", prototype)
            self.assertIn("Preserved human edits and conflicts", prototype)
            self.assertIn("Revised agent draft.", prototype)

    def test_blueprint_revision_marks_direct_human_edit_in_history(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._prd_project(project_dir)
            blueprint_path = Path(project_dir, "review-blueprint.md")
            blueprint_path.write_text(
                blueprint_path.read_text(encoding="utf-8").replace(
                    "- ligand class\n- substrate class",
                    "- ligand class\n- substrate class\n- HUMAN EDIT: solvent coordination",
                ),
                encoding="utf-8",
            )

            orchestrator.revise_review_blueprint(
                {
                    "comparison_dimensions": (
                        "ligand class",
                        "substrate class",
                        "solvent coordination",
                        "catalyst speciation",
                    )
                },
                evidence_note="New spectroscopy evidence supports adding catalyst speciation.",
            )

            revised = blueprint_path.read_text(encoding="utf-8")
            self.assertIn("Direct human edit detected", revised)
            self.assertIn("HUMAN EDIT: solvent coordination", revised)

    def test_blueprint_rejects_blank_required_sequence_items(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._prototype_ready_project(project_dir)
            orchestrator.run_prototype(
                PrototypeSubmission(
                    paper_ids=("paper-1", "paper-2"),
                    representative_reason="The pair spans the anchor claim and counterevidence.",
                    value_argument="The evidence supports a condition-centred comparison.",
                    signals=(
                        PrototypeSignal(
                            kind="comparison",
                            statement="Compare ligand and substrate contexts.",
                            evidence_ids=("paper-1", "paper-2"),
                            value_gain="Tests whether the disagreement is context-dependent.",
                        ),
                    ),
                    risks=("Sparse condition reporting.",),
                )
            )
            orchestrator.accept_prototype_handoff()

            with self.assertRaisesRegex(ValueError, "comparison_dimensions"):
                orchestrator.build_review_blueprint(
                    BlueprintProposal(
                        section_structure=("Mechanistic context",),
                        narrative_line="Explain context-dependent mechanistic branches.",
                        comparison_dimensions=("",),
                        evidence_strategy=("Anchor evidence",),
                        target_journal_requirements=("Journal requirements remain open.",),
                        known_risks=("Uneven reporting.",),
                        candidate_units=("Build comparison table",),
                    )
                )

    def _prd_project(self, project_dir):
        orchestrator = self._prototype_ready_project(project_dir)
        orchestrator.run_prototype(
            PrototypeSubmission(
                paper_ids=("paper-1", "paper-2"),
                representative_reason="The pair spans the anchor claim and its counterevidence.",
                value_argument="The condition-centred comparison can reconcile an apparent contradiction.",
                signals=(
                    PrototypeSignal(
                        kind="comparison",
                        statement="Compare ligand, substrate, and mechanistic probe.",
                        evidence_ids=("paper-1", "paper-2"),
                        value_gain="Tests whether the contradiction is condition-dependent.",
                    ),
                ),
                risks=("Sparse operando evidence.",),
            )
        )
        orchestrator.accept_prototype_handoff()
        orchestrator.build_review_blueprint(
            BlueprintProposal(
                section_structure=("Problem and vocabulary", "Mechanistic branches"),
                narrative_line="Move from apparent contradiction to condition-dependent branches.",
                comparison_dimensions=("ligand class", "substrate class"),
                evidence_strategy=("Anchor studies", "Counterevidence"),
                target_journal_requirements=("Target journal remains to be confirmed.",),
                known_risks=("Uneven catalyst-speciation reporting.",),
                candidate_units=("Build condition-comparability table",),
            )
        )
        return orchestrator

    def _prototype_ready_project(self, project_dir):
        orchestrator = ChemicalReviewOrchestrator(project_dir)
        orchestrator.start("nickel-catalyzed cross-coupling mechanisms")
        orchestrator.continue_grill(
            {
                "core_claims": "Mechanistic pathways depend on ligand and substrate context.",
                "scope": "Nickel-catalyzed C-C cross-coupling",
                "exclusions": "Palladium-only systems",
                "audience": "Organometallic chemistry researchers",
                "contribution": "Reconcile apparently conflicting mechanistic evidence",
                "researcher_context": "No prior context beyond the stated nickel coupling scope.",
                "evidence_standards": "Primary papers with legal full-text page or section locators.",
                "boundary_scenarios": "Treat unmatched ligands, substrates, and locators as gaps.",
            }
        )
        orchestrator.confirm_current_intent()
        orchestrator.run_research(ResearchConfig(discovery=(DiscoveryFixture(),)))
        orchestrator.accept_research_handoff()
        self.assertEqual(orchestrator.resume().phase, "PROTOTYPE")
        return orchestrator


if __name__ == "__main__":
    unittest.main()
