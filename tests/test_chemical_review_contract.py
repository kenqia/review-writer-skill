from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "chemical-review"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "chemical-review"

sys.path.insert(0, str(SKILL_DIR))
from orchestrator import ChemicalReviewOrchestrator  # noqa: E402


class ChemicalReviewContractTests(unittest.TestCase):
    def test_skill_is_user_invoked_and_discloses_workflow_references(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: chemical-review", skill)
        self.assertIn("disable-model-invocation: true", skill)
        self.assertIn("WORKFLOW.md", skill)
        self.assertIn("ASSET-TEMPLATES.md", skill)

    def test_workflow_declares_the_single_orchestrator_contract(self):
        workflow = (SKILL_DIR / "WORKFLOW.md").read_text(encoding="utf-8")
        for term in (
            "single user-facing seam",
            "GRILL",
            "RESEARCH",
            "HUMAN_ACTION_REQUIRED",
            "review-intent.md",
            "domain-profile.md",
            "workflow-state.md",
            "explicit confirmation",
        ):
            self.assertIn(term, workflow)

    def test_asset_templates_have_required_sections(self):
        templates = (SKILL_DIR / "ASSET-TEMPLATES.md").read_text(encoding="utf-8")
        expected_sections = {
            "review-intent.md": ("Research question", "Scope", "Expected contribution"),
            "domain-profile.md": ("Chemical subfield", "Core systems", "Evidence expectations"),
            "workflow-state.md": ("phase:", "next_action:", "intent_confirmation:"),
        }
        for filename, sections in expected_sections.items():
            self.assertIn(filename, templates)
            for section in sections:
                self.assertIn(section, templates)

    def test_behavior_fixtures_cover_the_ticket(self):
        required = {
            "fresh-start.md": ("topic-only start", "review-intent.md", "domain-profile.md"),
            "missing-information.md": ("open questions", "continue Grill"),
            "resume.md": ("cold restart", "next_action"),
            "confirmed-intent-change.md": ("explicit confirmation", "intent_revision"),
        }
        for filename, terms in required.items():
            fixture = (FIXTURE_DIR / filename).read_text(encoding="utf-8")
            for term in terms:
                self.assertIn(term, fixture)

    def test_state_template_uses_a_bounded_phase_vocabulary(self):
        templates = (SKILL_DIR / "ASSET-TEMPLATES.md").read_text(encoding="utf-8")
        phase_line = next(line for line in templates.splitlines() if line.startswith("phase:"))
        phases = set(re.findall(r"[A-Z][A-Z_]+", phase_line))
        self.assertTrue({"GRILL", "RESEARCH", "REVIEW"}.issubset(phases))

    def test_topic_only_start_persists_guided_grill_assets(self):
        with TemporaryDirectory() as project_dir:
            result = ChemicalReviewOrchestrator(project_dir).start("electrochemical CO2 reduction")

            self.assertEqual(result.phase, "GRILL")
            self.assertEqual(result.status, "ACTIVE")
            self.assertIn("research question", result.next_action.lower())
            for filename in ("review-intent.md", "domain-profile.md", "workflow-state.md"):
                self.assertTrue((Path(project_dir) / filename).exists())
            intent = (Path(project_dir) / "review-intent.md").read_text(encoding="utf-8")
            self.assertIn("electrochemical CO2 reduction", intent)
            self.assertIn("Core-claim candidates", intent)

    def test_missing_information_stays_in_grill_with_open_questions(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("catalytic biomass valorization")
            result = orchestrator.continue_grill({"scope": "heterogeneous catalysts only"})

            self.assertEqual(result.phase, "GRILL")
            self.assertEqual(result.status, "ACTIVE")
            self.assertIn("continue Grill", result.next_action)
            intent = (Path(project_dir) / "review-intent.md").read_text(encoding="utf-8")
            self.assertIn("open questions", intent.lower())
            self.assertIn("expected contribution", intent.lower())

    def test_resume_reads_saved_state_after_cold_restart(self):
        with TemporaryDirectory() as project_dir:
            first = ChemicalReviewOrchestrator(project_dir)
            first.start("solid-state battery interfaces")
            first.continue_grill(
                {
                    "research_question": "How do interphases control ion transport?",
                    "core_claims": "Interphase chemistry mediates rate and lifetime.",
                    "scope": "2020 onward; sulfide and oxide interfaces",
                    "exclusions": "No device economics",
                    "audience": "Electrochemistry researchers",
                    "contribution": "A mechanism-centred comparison",
                }
            )

            resumed = ChemicalReviewOrchestrator(project_dir).resume()
            self.assertEqual(resumed.phase, "GRILL")
            self.assertEqual(resumed.status, "READY_FOR_NEXT_PHASE")
            self.assertIn("Confirm", resumed.next_action)
            self.assertEqual(resumed.assets["intent_revision"], "0")

    def test_confirmed_intent_change_preserves_history_and_increments_revision(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("photocatalytic nitrogen fixation")
            orchestrator.continue_grill(
                {
                    "scope": "aqueous photocatalytic systems",
                    "exclusions": "Thermal Haber-Bosch chemistry",
                    "core_claims": "Charge separation is the main bottleneck.",
                    "audience": "Photochemistry researchers",
                    "contribution": "Connect materials descriptors to selectivity.",
                }
            )
            pending = orchestrator.propose_intent_change(
                {"scope": "aqueous and gas-phase photocatalytic systems"}
            )
            self.assertEqual(pending.status, "WAITING_FOR_HUMAN")
            self.assertEqual(pending.human_action, "REQUIRED")
            before = (Path(project_dir) / "review-intent.md").read_text(encoding="utf-8")
            self.assertIn("aqueous photocatalytic systems", before)

            confirmed = orchestrator.confirm_intent_change(accept=True)
            self.assertEqual(confirmed.status, "ACTIVE")
            self.assertEqual(confirmed.intent_revision, 1)
            intent = (Path(project_dir) / "review-intent.md").read_text(encoding="utf-8")
            self.assertIn("aqueous and gas-phase photocatalytic systems", intent)
            self.assertIn("Intent revision history", intent)
            self.assertNotIn("Pending intent change", intent)


if __name__ == "__main__":
    unittest.main()
