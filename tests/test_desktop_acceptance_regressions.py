from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "chemical-review"
sys.path.insert(0, str(SKILL_DIR))

from delivery import DocxExportError  # noqa: E402
from orchestrator import ChemicalReviewOrchestrator  # noqa: E402
from research import ResearchConfig  # noqa: E402


class DesktopAcceptanceRegressionTests(unittest.TestCase):
    def test_legacy_execution_modes_normalize_to_one_canonical_route(self):
        for mode in (None, "acceptance", "continuous"):
            with self.subTest(mode=mode), TemporaryDirectory() as project_dir:
                result = ChemicalReviewOrchestrator(project_dir).start(
                    "ligand effects in nickel-mediated C-C coupling",
                    mode=mode,
                )

                self.assertEqual(result.execution_mode, "canonical")
                state = Path(project_dir, "workflow-state.md").read_text(encoding="utf-8")
                self.assertIn("execution_mode: canonical", state)

    def test_grill_does_not_confirm_without_context_and_evidence_answers(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("topic-only chemistry review")

            partial = orchestrator.continue_grill(
                {
                    "core_claims": "Ligand effects are condition dependent.",
                    "scope": "Nickel-mediated C-C coupling",
                    "exclusions": "Palladium-only systems",
                    "audience": "Chemistry researchers",
                    "contribution": "Expose comparability boundaries.",
                }
            )

            self.assertEqual(partial.status, "ACTIVE")
            self.assertEqual(partial.intent_confirmation, "REQUIRED")
            self.assertIn("Researcher context", partial.next_action)
            self.assertIn("Evidence standards", partial.next_action)

    def test_grill_persists_answer_provenance_and_explicit_unknowns(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("topic-only chemistry review")
            result = orchestrator.continue_grill(
                {
                    "core_claims": "Ligand effects are condition dependent.",
                    "scope": "Nickel-mediated C-C coupling",
                    "exclusions": "Palladium-only systems",
                    "audience": "Chemistry researchers",
                    "contribution": "Expose comparability boundaries.",
                    "researcher_context": "UNKNOWN",
                    "evidence_standards": "Primary PDF locators; UNKNOWN for missing details.",
                    "boundary_scenarios": "UNKNOWN",
                }
            )

            self.assertEqual(result.status, "READY_FOR_NEXT_PHASE")
            intent = Path(project_dir, "review-intent.md").read_text(encoding="utf-8")
            self.assertIn("## Answer provenance", intent)
            self.assertIn("Researcher context and prior knowledge: USER", intent)
            self.assertIn("Evidence standards and constraints: USER", intent)
            self.assertIn("Boundary scenarios: USER", intent)
            self.assertIn("UNKNOWN", intent)

    def test_docx_export_requires_a_canonical_delivery_ready_state(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("topic-only chemistry review")

            with self.assertRaisesRegex(DocxExportError, "canonical delivery-ready"):
                orchestrator.export_docx()

    def test_canonical_cycle_advances_research_without_an_ordinary_pause(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("topic-only chemistry review")
            orchestrator.continue_grill(
                {
                    "core_claims": "Ligand effects depend on reaction context.",
                    "scope": "Nickel-mediated C-C coupling",
                    "exclusions": "Palladium-only systems",
                    "audience": "Chemistry researchers",
                    "contribution": "Expose comparability boundaries.",
                    "researcher_context": "No prior context beyond the stated scope.",
                    "evidence_standards": "Primary sources with stable page or section locators.",
                    "boundary_scenarios": "Treat unmatched conditions as non-comparable.",
                }
            )
            orchestrator.confirm_current_intent()

            result = orchestrator.run_cycle(
                research_config=ResearchConfig.no_key_fallback()
            )

            self.assertEqual(result.execution_mode, "canonical")
            self.assertEqual(result.phase, "PROTOTYPE")
            self.assertEqual(result.status, "ACTIVE")
            self.assertNotIn("Confirm the Research handoff", result.next_action)
            ledger = json.loads(Path(project_dir, "run-budget.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["user_pause_count"], 0)
            self.assertGreaterEqual(ledger["orchestration_event_count"], 2)

    def test_ledger_separates_user_pauses_from_internal_events(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("topic-only chemistry review")
            orchestrator.record_user_pause(phase="GRILL")
            orchestrator.record_orchestration_event("delegate", phase="GRILL")
            orchestrator.record_orchestration_event("wait", phase="GRILL")

            ledger = json.loads(Path(project_dir, "run-budget.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["user_pause_count"], 1)
            self.assertEqual(ledger["orchestration_event_count"], 2)
            self.assertEqual(
                [event["event"] for event in ledger["orchestration_events"]],
                ["delegate", "wait"],
            )
            projection = Path(project_dir, "run-ledger.md").read_text(encoding="utf-8")
            self.assertIn("user_pause_count: 1", projection)
            self.assertIn("orchestration_event_count: 2", projection)


if __name__ == "__main__":
    unittest.main()
