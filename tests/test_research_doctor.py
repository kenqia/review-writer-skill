import json
import hashlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "chemical-review"
sys.path.insert(0, str(SKILL_DIR))

from orchestrator import ChemicalReviewOrchestrator  # noqa: E402
from delivery import FigureInventory  # noqa: E402
import research as _research  # noqa: E402

FullTextResult = _research.FullTextResult
LocalPdftotextParserAdapter = _research.LocalPdftotextParserAdapter
PaperRecord = _research.PaperRecord
ParsedMedia = _research.ParsedMedia
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

    def __init__(self, text="authorized text"):
        self.text = text
        self.calls = []

    def fetch(self, paper):
        self.calls.append(paper.identifier)
        return FullTextResult(
            paper.identifier,
            "FOUND",
            self.text,
            self.name,
            locator=f"fixture://{paper.identifier}.pdf",
            access_basis="OPEN_ACCESS",
        )


class _LocalParser:
    name = "MinerU"

    def __init__(self):
        self.calls = []

    def parse(self, full_text):
        self.calls.append(full_text.paper_id)
        return _research.ParsedDocument(
            full_text.paper_id,
            self.name,
            sections=("Results",),
            locators=("p. 1",),
        )


class _MediaParser:
    name = "MinerU"

    def __init__(self, source_path):
        self.source_path = source_path

    def parse(self, full_text):
        return _research.ParsedDocument(
            full_text.paper_id,
            self.name,
            sections=("Results",),
            locators=("p. 2",),
            media=(
                ParsedMedia(
                    asset_id="fig-research-1",
                    asset_type="FIGURE",
                    source_path=str(self.source_path),
                    locator="p. 2, Figure 1",
                    caption="Source-bound research figure.",
                ),
            ),
        )


class _CloudParser:
    name = "CloudParser"
    cloud = True

    def __init__(self):
        self.calls = []

    def parse(self, full_text):
        self.calls.append(full_text.paper_id)
        raise AssertionError("a cloud parser must not receive a user PDF without consent")


class _ConsentedCloudParser:
    name = "CloudParser"
    cloud = True

    def __init__(self):
        self.calls = []

    def parse(self, full_text):
        self.calls.append(full_text.paper_id)
        return _research.ParsedDocument(
            full_text.paper_id,
            self.name,
            sections=("Results",),
            locators=("p. 2",),
        )


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

    def test_no_key_fallback_connects_detected_local_pdftotext_parser(self):
        with patch.object(_research.shutil, "which", return_value="/usr/bin/pdftotext"):
            config = ResearchConfig.no_key_fallback()

        self.assertEqual(
            [adapter.name for adapter in config.parsers],
            ["pdftotext"],
        )

    def test_local_pdftotext_parser_emits_page_locators_and_chunk_count(self):
        document = LocalPdftotextParserAdapter().parse(
            FullTextResult(
                paper_id="local-pdf:fixture",
                status="FOUND",
                text="INTRODUCTION\nFirst page.\fRESULTS\nSecond page.\f",
                source="UserAuthorizedPDF",
                locator="paper.pdf#local-pdf",
                access_basis="USER_AUTHORIZED",
                local_path="paper.pdf",
            )
        )

        self.assertEqual(document.parser, "pdftotext")
        self.assertEqual(document.locators, ("paper.pdf#page=1", "paper.pdf#page=2"))
        self.assertEqual(len(document.sections), 2)
        self.assertIn("INTRODUCTION", document.sections[0])

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

    def test_explicit_cloud_parser_consent_is_project_persisted(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._ready(project_dir)
            cloud = _ConsentedCloudParser()

            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(_Discovery((PaperRecord("p-consent", "Consent paper"),)),),
                    full_text=(_FullText(),),
                    parsers=(cloud,),
                    cloud_parser_consent=True,
                    run_id="consent-run",
                )
            )

            self.assertEqual(cloud.calls, ["p-consent"])
            self.assertEqual(result.assets["cloud_parser_consent"], "GRANTED")
            consent_path = Path(result.assets["cloud_parser_consent_asset"])
            self.assertTrue(consent_path.is_file())
            consent = consent_path.read_text(encoding="utf-8")
            self.assertIn("kind: project-pdf-parser-consent", consent)
            self.assertIn("run_id: consent-run", consent)
            self.assertEqual(
                ChemicalReviewOrchestrator(project_dir).resume().assets[
                    "cloud_parser_consent"
                ],
                "GRANTED",
            )

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
            self.assertIn('"parser_chunks": 0', ledger)
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
            events = json.loads(ledger)["events"]
            reused = [event for event in events if event.get("outcome") == "REUSED"]
            self.assertTrue(reused)
            self.assertTrue(all(len(event["artifact_id"]) == 64 for event in reused))

    def test_parsed_media_is_persisted_with_source_and_asset_digests(self):
        with TemporaryDirectory() as project_dir:
            root = Path(project_dir)
            image_path = root / "parsed-figure.png"
            Image.new("RGB", (64, 48), "white").save(image_path)
            orchestrator = self._ready(project_dir)

            orchestrator.run_research(
                ResearchConfig(
                    discovery=(_Discovery((PaperRecord("p-media", "Media paper"),)),),
                    full_text=(_FullText(),),
                    parsers=(_MediaParser(image_path),),
                )
            )

            inventory = FigureInventory.load(root)
            asset = inventory.assets["fig-research-1"]
            self.assertEqual(asset.status, "SOURCE")
            self.assertEqual(asset.extraction_status, "VERIFIED")
            self.assertEqual(
                asset.sha256,
                hashlib.sha256(image_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                asset.source_digest,
                hashlib.sha256(b"authorized text").hexdigest(),
            )
            registry = (root / "source-registry.md").read_text(encoding="utf-8")
            self.assertIn(asset.source_id, registry)
            self.assertIn(asset.asset_id, registry)
            ledger = json.loads((root / "run-budget.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["parser_chunks"], 1)

    def test_cached_parse_records_reused_chunk_count(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._ready(project_dir)
            discovery = _Discovery((PaperRecord("p-chunks", "P"),))
            full_text = _FullText("authorized text")
            parser = _LocalParser()
            config = ResearchConfig(
                discovery=(discovery,),
                full_text=(full_text,),
                parsers=(parser,),
                budget=ResearchBudget(max_queries=10, max_requests=20),
            )
            orchestrator.run_research(config)

            ChemicalReviewOrchestrator(project_dir).run_research(config)

            ledger = json.loads(
                Path(project_dir, "run-budget.json").read_text(encoding="utf-8")
            )
            self.assertEqual(parser.calls, ["p-chunks"])
            self.assertEqual(ledger["parser_chunks"], 1)

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

    def test_cached_full_text_cannot_bypass_current_output_budget(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._ready(project_dir)
            discovery = _Discovery((PaperRecord("p-cache", "P"),))
            full_text = _FullText("authorized full text " * 20)
            parser = _LocalParser()
            orchestrator.run_research(
                ResearchConfig(
                    discovery=(discovery,),
                    full_text=(full_text,),
                    parsers=(parser,),
                    budget=ResearchBudget(max_queries=10, max_requests=20),
                )
            )

            result = ChemicalReviewOrchestrator(project_dir).run_research(
                ResearchConfig(
                    discovery=(discovery,),
                    full_text=(full_text,),
                    parsers=(parser,),
                    budget=ResearchBudget(
                        max_queries=10,
                        max_requests=20,
                        max_output_tokens=4,
                    ),
                )
            )

            self.assertEqual(result.assets["readiness"], "DISCOVERY_READY")
            self.assertEqual(full_text.calls, ["p-cache"])
            self.assertEqual(parser.calls, ["p-cache"])
            evidence = Path(project_dir, "research-evidence.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("cached full-text", evidence)
            ledger = json.loads(
                Path(project_dir, "run-budget.json").read_text(encoding="utf-8")
            )
            self.assertGreater(ledger["output_tokens"], 0)
            self.assertLessEqual(ledger["output_tokens"], 4)

    def test_cached_parse_cannot_bypass_current_parser_page_budget(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._ready(project_dir)
            discovery = _Discovery((PaperRecord("p-pages", "P"),))
            full_text = _FullText("authorized text")
            parser = _LocalParser()
            orchestrator.run_research(
                ResearchConfig(
                    discovery=(discovery,),
                    full_text=(full_text,),
                    parsers=(parser,),
                    budget=ResearchBudget(max_queries=10, max_requests=20),
                )
            )

            result = ChemicalReviewOrchestrator(project_dir).run_research(
                ResearchConfig(
                    discovery=(discovery,),
                    full_text=(full_text,),
                    parsers=(parser,),
                    budget=ResearchBudget(
                        max_queries=10,
                        max_requests=20,
                        max_parser_pages=0,
                    ),
                )
            )

            self.assertEqual(result.assets["readiness"], "DISCOVERY_READY")
            self.assertEqual(full_text.calls, ["p-pages"])
            self.assertEqual(parser.calls, ["p-pages"])
            evidence = Path(project_dir, "research-evidence.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("cached parsed document", evidence)
            ledger = json.loads(
                Path(project_dir, "run-budget.json").read_text(encoding="utf-8")
            )
            self.assertEqual(ledger["parser_chunks"], 0)


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
