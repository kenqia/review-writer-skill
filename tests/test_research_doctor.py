from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "chemical-review"
sys.path.insert(0, str(SKILL_DIR))

from orchestrator import ChemicalReviewOrchestrator  # noqa: E402
import research as _research  # noqa: E402

FullTextResult = _research.FullTextResult
PaperRecord = _research.PaperRecord
ResearchConfig = _research.ResearchConfig


class _MissingResearchBudget:
    def __init__(self, *args, **kwargs):
        raise AssertionError("ResearchBudget is not implemented")


ResearchBudget = getattr(_research, "ResearchBudget", _MissingResearchBudget)


class _Discovery:
    name = "Crossref"

    def __init__(self, papers):
        self.papers = tuple(papers)
        self.calls = []

    def search(self, query, path):
        self.calls.append((query, path))
        return self.papers


class _FullText:
    name = "Unpaywall"

    def fetch(self, paper):
        return FullTextResult(
            paper.identifier,
            "FOUND",
            "authorized text",
            self.name,
            locator=f"fixture://{paper.identifier}.pdf",
            access_basis="OPEN_ACCESS",
        )


class _CloudParser:
    name = "CloudParser"
    cloud = True

    def __init__(self):
        self.calls = []

    def parse(self, full_text):
        self.calls.append(full_text.paper_id)
        raise AssertionError("a cloud parser must not receive a user PDF without consent")


class ResearchDoctorContractTests(unittest.TestCase):
    def _ready(self, project_dir):
        orchestrator = ChemicalReviewOrchestrator(project_dir)
        orchestrator.start("condition-dependent nickel coupling")
        orchestrator.continue_grill(
            {
                "core_claims": "Mechanism varies with ligand and substrate context.",
                "scope": "Nickel-mediated C-C coupling",
                "exclusions": "Palladium-only systems",
                "audience": "Organometallic chemists",
                "contribution": "Reconcile competing mechanistic models",
            }
        )
        orchestrator.confirm_current_intent()
        return orchestrator

    def test_topic_start_extracts_known_facts_and_only_asks_frontier_gaps(self):
        with TemporaryDirectory() as project_dir:
            proposal = (
                "# Proposal\n\n"
                "## Research question\nHow do ligands redirect nickel coupling?\n\n"
                "## Scope and exclusions\nScope: C-C coupling.\nExclusions: palladium-only systems.\n\n"
                "## Audience or target journal\nTarget reader: organometallic chemists.\n\n"
                "## Unrelated private note\nemail: hidden@example.invalid\n"
            )
            start = ChemicalReviewOrchestrator(project_dir).start
            if "materials" not in __import__("inspect").signature(start).parameters:
                self.fail("start(materials=...) is not implemented")
            result = start("nickel coupling", materials={"proposal.md": proposal})

            intent = Path(project_dir, "review-intent.md").read_text(encoding="utf-8")
            self.assertIn("Known facts", intent)
            self.assertIn("How do ligands redirect nickel coupling?", intent)
            self.assertIn("palladium-only systems", intent)
            self.assertNotIn("hidden@example.invalid", intent)
            self.assertNotIn("Research question", "\n".join(result.frontier_questions))
            self.assertTrue(any("core claim" in question.lower() for question in result.frontier_questions))

            resumed = ChemicalReviewOrchestrator(project_dir).resume()
            self.assertEqual(resumed.frontier_questions, result.frontier_questions)
            self.assertIn("known facts", resumed.assets["next_action"].lower() + intent.lower())

    def test_no_key_fallback_keeps_bounded_research_available(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._ready(project_dir)
            no_key_factory = getattr(ResearchConfig, "no_key_fallback", None)
            if no_key_factory is None:
                self.fail("ResearchConfig.no_key_fallback is not implemented")
            result = orchestrator.run_research(no_key_factory())

            self.assertEqual(result.status, "READY_FOR_NEXT_PHASE")
            self.assertEqual(result.human_action, "NONE")
            self.assertEqual(result.assets["research_handoff"], "PROTOTYPE")
            evidence = Path(project_dir, "research-evidence.md").read_text(encoding="utf-8")
            self.assertIn("NO_KEY_FALLBACK", evidence)
            self.assertIn("bounded discovery", evidence.lower())
            self.assertTrue(Path(project_dir, "research-setup-wizard.md").exists())

    def test_user_pdf_is_registered_and_cloud_parser_requires_project_consent(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._ready(project_dir)
            pdf_path = Path(project_dir, "authorized-paper.pdf")
            pdf_path.write_bytes(b"%PDF-1.7 authorized fixture")
            cloud = _CloudParser()
            fields = ResearchConfig.__dataclass_fields__
            if "user_pdfs" not in fields or "cloud_parser_consent" not in fields:
                self.fail("ResearchConfig user-PDF consent fields are not implemented")
            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(_Discovery((PaperRecord("p1", "Public paper"),)),),
                    full_text=(_FullText(),),
                    parsers=(cloud,),
                    user_pdfs=(pdf_path,),
                    cloud_parser_consent=False,
                )
            )

            self.assertEqual(cloud.calls, [])
            registry = Path(project_dir, "source-registry.md").read_text(encoding="utf-8")
            self.assertIn("authorized-paper.pdf", registry)
            self.assertIn("USER_AUTHORIZED", registry)
            self.assertIn("CloudParser", registry)
            self.assertIn("consent", registry.lower())
            self.assertIn("source_registry", result.assets)

    def test_budget_stopping_and_ledger_report_marginal_coverage(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._ready(project_dir)
            discovery = _Discovery((PaperRecord("p1", "One candidate"),))
            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(discovery,),
                    budget=ResearchBudget(max_queries=2, max_requests=2),
                )
            )

            self.assertLessEqual(len(discovery.calls), 2)
            coverage = Path(project_dir, "coverage-matrix.md").read_text(encoding="utf-8")
            self.assertIn("Marginal gain", coverage)
            self.assertIn("Stopping reason", coverage)
            ledger = Path(project_dir, "run-budget.json").read_text(encoding="utf-8")
            self.assertIn('"query_count"', ledger)
            self.assertIn('"request_count"', ledger)
            self.assertIn('"cache_hits"', ledger)
            self.assertIn("coverage", result.assets)

    def test_identical_run_reuses_query_cache_after_cold_restart(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._ready(project_dir)
            discovery = _Discovery((PaperRecord("p1", "Cached candidate"),))
            config = ResearchConfig(discovery=(discovery,), budget=ResearchBudget(max_queries=1))
            orchestrator.run_research(config)
            first_call_count = len(discovery.calls)

            resumed = ChemicalReviewOrchestrator(project_dir)
            resumed.run_research(config)
            self.assertEqual(len(discovery.calls), first_call_count)
            ledger = Path(project_dir, "run-budget.json").read_text(encoding="utf-8")
            self.assertIn('"cache_hits":', ledger)
            self.assertRegex(ledger, r'"cache_hits":\s*[1-9]')

    def test_output_budget_rejection_is_not_cached_as_a_free_result(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._ready(project_dir)
            discovery = _Discovery((PaperRecord("p-budget", "A deliberately long candidate title"),))
            config = ResearchConfig(
                discovery=(discovery,),
                budget=ResearchBudget(max_queries=1, max_output_tokens=1),
            )
            first = orchestrator.run_research(config)
            self.assertEqual(first.assets["readiness"], "DISCOVERY_READY")
            ChemicalReviewOrchestrator(project_dir).run_research(config)
            self.assertGreaterEqual(len(discovery.calls), 2)


class ResearchDoctorProductUseAcceptanceTests(unittest.TestCase):
    """Narrow user-visible acceptance slices for ticket #19's Research seam."""

    def _complete_grill(self, project_dir, topic):
        orchestrator = ChemicalReviewOrchestrator(project_dir)
        started = orchestrator.start(topic, mode="continuous")
        self.assertEqual(started.execution_mode, "continuous")
        grilled = orchestrator.continue_grill(
            {
                "core_claims": "Mechanistic branches depend on reaction context.",
                "scope": "The named chemistry and its reported mechanistic variants",
                "exclusions": "Unrelated reaction families",
                "audience": "Chemistry researchers",
                "contribution": "Expose evidence gaps and competing explanations",
            }
        )
        self.assertEqual(grilled.execution_mode, "continuous")
        confirmed = orchestrator.confirm_current_intent()
        self.assertEqual(confirmed.phase, "RESEARCH")
        self.assertEqual(confirmed.execution_mode, "continuous")
        return orchestrator

    def test_product_use_topic_only_continuous_no_key_research_is_honest_and_resumable(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._complete_grill(
                project_dir, "topic-only mechanistic chemistry review"
            )

            result = orchestrator.run_research(ResearchConfig.no_key_fallback())

            self.assertEqual(result.phase, "RESEARCH")
            self.assertEqual(result.status, "READY_FOR_NEXT_PHASE")
            self.assertEqual(result.assets["readiness"], "DISCOVERY_READY")
            self.assertIn("NO_KEY_FALLBACK", Path(project_dir, "research-evidence.md").read_text(encoding="utf-8"))
            self.assertEqual(Path(result.assets["source_registry"]).name, "source-registry.md")
            self.assertTrue(Path(project_dir, "source-registry.md").exists())
            self.assertIn("bounded no-key", result.next_action.lower())
            resumed = ChemicalReviewOrchestrator(project_dir).resume()
            self.assertEqual(resumed.execution_mode, "continuous")
            self.assertEqual(resumed.assets["readiness"], "DISCOVERY_READY")

    def test_product_use_authorized_pdf_continuous_no_key_preserves_source_registry(self):
        with TemporaryDirectory() as project_dir:
            pdf_path = Path(project_dir, "authorized-input.pdf")
            pdf_path.write_bytes(b"%PDF-1.7 authorized product-use fixture")
            orchestrator = self._complete_grill(
                project_dir, "topic plus authorized PDF chemistry review"
            )

            result = orchestrator.run_research(
                ResearchConfig.no_key_fallback(user_pdfs=(pdf_path,))
            )

            registry = Path(project_dir, "source-registry.md").read_text(encoding="utf-8")
            self.assertEqual(result.phase, "RESEARCH")
            self.assertEqual(result.assets["readiness"], "DISCOVERY_READY")
            self.assertIn("authorized-input.pdf", registry)
            self.assertIn("USER_AUTHORIZED", registry)
            self.assertIn("NO_KEY_FALLBACK", Path(project_dir, "research-evidence.md").read_text(encoding="utf-8"))
            self.assertIn("authorized pdfs", result.next_action.lower())


if __name__ == "__main__":
    unittest.main()
