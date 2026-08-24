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
from research import (  # noqa: E402
    CapabilityUnavailable,
    FullTextResult,
    ParsedDocument,
    PaperRecord,
    ResearchConfig,
)


class FakeDiscovery:
    def __init__(self, name, papers=None, error=None):
        self.name = name
        self.papers = papers or []
        self.error = error
        self.calls = []

    def search(self, query, path):
        self.calls.append((query, path))
        if self.error:
            raise self.error
        return [
            PaperRecord(
                identifier=paper.identifier,
                title=paper.title,
                authors=paper.authors,
                year=paper.year,
                source=self.name,
                layer=paper.layer,
                abstract=paper.abstract,
                doi=paper.doi,
                keywords=paper.keywords,
                cited_identifiers=paper.cited_identifiers,
            )
            for paper in self.papers
        ]


class FakeEntity:
    def __init__(self, name, terms=None, error=None):
        self.name = name
        self.terms = terms or []
        self.error = error

    def expand(self, term):
        if self.error:
            raise self.error
        return self.terms


class FakeFullText:
    def __init__(self, name, text=None, error=None, access_basis="OPEN_ACCESS"):
        self.name = name
        self.text = text
        self.error = error
        self.access_basis = access_basis

    def fetch(self, paper):
        if self.error:
            raise self.error
        if self.text is None:
            return FullTextResult(paper.identifier, "UNAVAILABLE", "", self.name)
        return FullTextResult(
            paper.identifier,
            "FOUND",
            self.text,
            self.name,
            locator=f"fixture://{paper.identifier}.pdf",
            access_basis=self.access_basis,
        )


class FakeParser:
    def __init__(self, name, error=None, locators=("section:Results",)):
        self.name = name
        self.error = error
        self.locators = locators
        self.calls = []

    def parse(self, full_text):
        self.calls.append(full_text.paper_id)
        if self.error:
            raise self.error
        return ParsedDocument(
            paper_id=full_text.paper_id,
            parser=self.name,
            sections=("Abstract", "Results", "References"),
            references=("10.1000/example",),
            locators=self.locators,
        )


class ChemicalReviewContractTests(unittest.TestCase):
    def test_skill_is_user_invoked_and_discloses_workflow_references(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: chemical-review", skill)
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

    def test_research_behavior_fixtures_cover_tool_and_handoff_paths(self):
        required = {
            "research-success.md": ("multi-path discovery", "layered literature set", "handoff"),
            "research-replacement.md": ("replaceable", "fallback", "degradation"),
            "research-tool-failure.md": ("HUMAN_ACTION_REQUIRED", "recovery"),
            "research-user-recovery.md": ("user-assisted", "rerun", "preserved"),
            "research-parse-degraded.md": ("MinerU", "GROBID", "Docling", "metadata"),
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
            self.assertIn("Continue Grill", result.next_action)
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
                    "researcher_context": "Prior work compares interphase chemistry and transport.",
                    "evidence_standards": "Primary papers with legal full-text page or section locators.",
                    "boundary_scenarios": "Treat unmatched interfaces and missing locators as non-comparable.",
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
                    "researcher_context": "No prior context beyond the stated photocatalysis question.",
                    "evidence_standards": "Primary papers and legal full text with explicit locators.",
                    "boundary_scenarios": "Separate aqueous and gas-phase systems when conditions differ.",
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

    def test_research_success_expands_paths_and_writes_layered_assets(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("perovskite solar cell stability")
            orchestrator.continue_grill(
                {
                    "core_claims": "Degradation is governed by coupled ion and interface chemistry.",
                    "scope": "Perovskite photovoltaic materials",
                    "exclusions": "Manufacturing economics",
                    "audience": "Materials chemistry researchers",
                    "contribution": "A mechanism-centred stability comparison",
                    "researcher_context": "No prior context beyond the stated materials scope.",
                    "evidence_standards": "Primary papers with legal full-text page or section locators.",
                    "boundary_scenarios": "Flag unmatched compositions and unavailable locators as gaps.",
                    "terms": "perovskite; metal halide; PSC",
                    "core_systems": "absorber, transport layer, and their interfaces",
                }
            )
            orchestrator.confirm_current_intent()
            papers = [PaperRecord("p1", "Anchor paper", layer="anchor/core", year=2024)]
            openalex = FakeDiscovery("OpenAlex", papers)
            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(openalex, FakeDiscovery("Crossref", papers)),
                    entities=(FakeEntity("PubChem", ["halide perovskite", "metal halide"]),),
                    full_text=(FakeFullText("Unpaywall", "full text"),),
                    parsers=(FakeParser("MinerU"),),
                )
            )

            self.assertEqual(result.phase, "RESEARCH")
            self.assertEqual(result.status, "READY_FOR_NEXT_PHASE")
            self.assertIn(result.assets["research_handoff"], {"PROTOTYPE", "PRD"})
            evidence = Path(project_dir, "research-evidence.md").read_text(encoding="utf-8")
            literature = Path(project_dir, "literature-set.md").read_text(encoding="utf-8")
            for path_name in (
                "synonyms",
                "definitions",
                "methods/materials",
                "key events",
                "citation relations",
                "authors/groups",
                "recent developments",
            ):
                self.assertIn(path_name, evidence)
            self.assertIn("Anchor/core", literature)
            self.assertIn("Anchor paper", literature)
            self.assertIn("MinerU", evidence)
            self.assertTrue(any("metal halide" in query for query, _ in openalex.calls))
            self.assertIn("absorber, transport layer", evidence)

    def test_research_tool_replacement_records_route_without_blocking(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("photoredox catalysis")
            orchestrator.continue_grill(
                {
                    "core_claims": "Photoredox selectivity depends on excited-state pathways.",
                    "scope": "Organic photoredox reactions",
                    "exclusions": "Biological photochemistry",
                    "audience": "Synthetic chemists",
                    "contribution": "Compare mechanistic descriptors across catalyst families",
                    "researcher_context": "No prior context beyond the stated photoredox scope.",
                    "evidence_standards": "Primary papers with legal full-text page or section locators.",
                    "boundary_scenarios": "Do not compare catalyst families without matched reaction conditions.",
                }
            )
            orchestrator.confirm_current_intent()
            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(FakeDiscovery("Semantic Scholar", [PaperRecord("p2", "Fallback paper")]),),
                    entities=(FakeEntity("ChEBI", ["photocatalyst"]),),
                    full_text=(FakeFullText("Europe PMC", "full text"),),
                    parsers=(FakeParser("GROBID"),),
                )
            )
            evidence = Path(project_dir, "research-evidence.md").read_text(encoding="utf-8")
            self.assertEqual(result.status, "READY_FOR_NEXT_PHASE")
            self.assertIn("OpenAlex", evidence)
            self.assertIn("Semantic Scholar", evidence)
            self.assertIn("GROBID", evidence)
            self.assertIn("replacement", evidence.lower())

    def test_research_total_discovery_failure_requests_user_recovery(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("electrocatalytic ammonia synthesis")
            orchestrator.continue_grill(
                {
                    "core_claims": "Surface structure controls nitrogen activation.",
                    "scope": "Electrocatalytic systems",
                    "exclusions": "Thermal catalysis",
                    "audience": "Electrochemists",
                    "contribution": "A cross-material mechanistic map",
                    "researcher_context": "No prior context beyond the stated electrocatalysis scope.",
                    "evidence_standards": "Primary papers with legal full-text page or section locators.",
                    "boundary_scenarios": "Treat different electrolytes and endpoints as non-comparable.",
                }
            )
            orchestrator.confirm_current_intent()
            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(
                        FakeDiscovery("OpenAlex", error=CapabilityUnavailable("missing API")),
                        FakeDiscovery("Semantic Scholar", error=CapabilityUnavailable("missing API")),
                    )
                )
            )
            self.assertEqual(result.status, "WAITING_FOR_HUMAN")
            self.assertEqual(result.human_action, "REQUIRED")
            self.assertIn("HUMAN_ACTION_REQUIRED", Path(project_dir, "research-evidence.md").read_text(encoding="utf-8"))
            self.assertIn("configure", result.next_action.lower())

    def test_research_recovers_after_user_configures_missing_route(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("solid electrolyte interfaces")
            orchestrator.continue_grill(
                {
                    "core_claims": "Interphase composition governs ion transport.",
                    "scope": "Solid-state electrolyte interfaces",
                    "exclusions": "Liquid electrolytes",
                    "audience": "Battery materials researchers",
                    "contribution": "Explain cross-study interface trends",
                    "researcher_context": "No prior context beyond the stated interface question.",
                    "evidence_standards": "Primary papers with legal full-text page or section locators.",
                    "boundary_scenarios": "Separate liquid and solid electrolyte systems.",
                }
            )
            orchestrator.confirm_current_intent()
            orchestrator.run_research(ResearchConfig(discovery=()))
            recovered = orchestrator.run_research(
                ResearchConfig(
                    discovery=(FakeDiscovery("Crossref", [PaperRecord("p3", "Recovered paper")]),),
                    full_text=(FakeFullText("CORE", "full text"),),
                    parsers=(FakeParser("Docling"),),
                )
            )
            self.assertEqual(recovered.status, "READY_FOR_NEXT_PHASE")
            literature = Path(project_dir, "literature-set.md").read_text(encoding="utf-8")
            self.assertIn("Recovered paper", literature)
            self.assertIn("Docling", Path(project_dir, "research-evidence.md").read_text(encoding="utf-8"))

    def test_research_parser_failure_keeps_metadata_and_documents_degradation(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("CO2 capture sorbents")
            orchestrator.continue_grill(
                {
                    "core_claims": "Pore chemistry controls selectivity and regeneration cost.",
                    "scope": "Porous solid sorbents",
                    "exclusions": "Aqueous amine absorption",
                    "audience": "Adsorption researchers",
                    "contribution": "Compare structure-property tradeoffs",
                    "researcher_context": "No prior context beyond the stated sorbent scope.",
                    "evidence_standards": "Primary papers with legal full-text page or section locators.",
                    "boundary_scenarios": "Do not merge aqueous and solid sorbent endpoints.",
                }
            )
            orchestrator.confirm_current_intent()
            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(FakeDiscovery("OpenAlex", [PaperRecord("p4", "Parser failure paper")]),),
                    full_text=(FakeFullText("Unpaywall", "full text"),),
                    parsers=(
                        FakeParser("MinerU", error=CapabilityUnavailable("parse failed")),
                        FakeParser("GROBID", error=CapabilityUnavailable("parse failed")),
                        FakeParser("Docling", error=CapabilityUnavailable("parse failed")),
                    ),
                )
            )
            self.assertEqual(result.status, "READY_FOR_NEXT_PHASE")
            self.assertEqual(result.human_action, "NONE")
            evidence = Path(project_dir, "research-evidence.md").read_text(encoding="utf-8")
            self.assertIn("parse failed", evidence)
            self.assertIn("full text: Unpaywall", evidence)
            self.assertIn("access basis: OPEN_ACCESS", evidence)
            self.assertIn("source locator: fixture://p4.pdf", evidence)
            self.assertIn("Parser failure paper", Path(project_dir, "literature-set.md").read_text(encoding="utf-8"))

    def test_research_handoff_acceptance_preserves_human_notes(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("heterogeneous hydrogenation")
            orchestrator.continue_grill(
                {
                    "core_claims": "Surface ensembles shape selectivity.",
                    "scope": "Heterogeneous hydrogenation catalysts",
                    "exclusions": "Homogeneous catalysis",
                    "audience": "Catalysis researchers",
                    "contribution": "Compare structure-selectivity explanations",
                    "researcher_context": "No prior context beyond the stated hydrogenation scope.",
                    "evidence_standards": "Primary papers with legal full-text page or section locators.",
                    "boundary_scenarios": "Keep homogeneous and heterogeneous systems separate.",
                }
            )
            orchestrator.confirm_current_intent()
            orchestrator.run_research(
                ResearchConfig(
                    discovery=(FakeDiscovery("OpenAlex", [PaperRecord("p5", "Human-note paper")]),),
                )
            )
            evidence_path = Path(project_dir, "research-evidence.md")
            evidence_path.write_text(
                evidence_path.read_text(encoding="utf-8").replace(
                    "## Human notes\n", "## Human notes\n- Compare this with the user's lab results.\n"
                ),
                encoding="utf-8",
            )
            handed_off = orchestrator.accept_research_handoff()
            self.assertEqual(handed_off.phase, "PROTOTYPE")
            self.assertIn("user's lab results", evidence_path.read_text(encoding="utf-8"))

    def test_low_risk_fully_configured_research_can_propose_prd(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._research_ready_project(project_dir)
            paper = PaperRecord("prd", "Well-scoped anchor")
            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(
                        FakeDiscovery("Crossref", [paper]),
                        FakeDiscovery("Semantic Scholar", [paper]),
                        FakeDiscovery("OpenAlex", [paper]),
                    ),
                    entities=(
                        FakeEntity("ChEBI", ["nickel complex"]),
                        FakeEntity("PubChem", ["nickel"]),
                    ),
                    full_text=(
                        FakeFullText("CORE", "full text"),
                        FakeFullText("Europe PMC", "full text"),
                        FakeFullText("Unpaywall", "full text"),
                    ),
                    parsers=(FakeParser("Docling"), FakeParser("GROBID"), FakeParser("MinerU")),
                )
            )
            self.assertEqual(result.assets["research_handoff"], "PRD")
            self.assertIn("Direct PRD", result.assets["research_handoff_rationale"])
            handed_off = orchestrator.accept_research_handoff()
            self.assertEqual(handed_off.phase, "PRD")

    def test_optional_pdftotext_gap_does_not_degrade_explicit_parser_route(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._research_ready_project(project_dir)
            paper = PaperRecord("explicit-parser", "Explicit parser route")
            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(
                        FakeDiscovery("Crossref", [paper]),
                        FakeDiscovery("Semantic Scholar", [paper]),
                        FakeDiscovery("OpenAlex", [paper]),
                    ),
                    entities=(FakeEntity("PubChem", ["nickel"]), FakeEntity("ChEBI", ["complex"])),
                    full_text=(
                        FakeFullText("CORE", "full text"),
                        FakeFullText("Europe PMC", "full text"),
                        FakeFullText("Unpaywall", "full text"),
                    ),
                    parsers=(FakeParser("MinerU"), FakeParser("GROBID"), FakeParser("Docling")),
                )
            )

            evidence = Path(project_dir, "research-evidence.md").read_text(encoding="utf-8")
            self.assertNotIn("PDF parsing / pdftotext: not configured", evidence)
            self.assertEqual(result.assets["research_handoff"], "PRD")

    def test_research_adapts_queries_and_classifies_unlayered_candidates(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._research_ready_project(project_dir)
            discovery = FakeDiscovery(
                "OpenAlex",
                [
                    PaperRecord(
                        "adaptive-1",
                        "Conflicting mechanisms in nickel catalysis",
                        authors=("A. Chemist",),
                        keywords=("oxidative addition", "radical pathway"),
                    )
                ],
            )
            orchestrator.run_research(ResearchConfig(discovery=(discovery,)))
            queries = [query for query, _ in discovery.calls]
            self.assertTrue(any("A. Chemist" in query for query in queries))
            self.assertTrue(any("radical pathway" in query for query in queries))
            literature = Path(project_dir, "literature-set.md").read_text(encoding="utf-8")
            self.assertIn("## Controversy", literature)
            self.assertIn("Conflicting mechanisms", literature)

    def test_research_rerun_keeps_previous_literature_candidates(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._research_ready_project(project_dir)
            orchestrator.run_research(
                ResearchConfig(discovery=(FakeDiscovery("OpenAlex", [PaperRecord("old", "Earlier candidate")]),))
            )
            orchestrator.run_research(
                ResearchConfig(discovery=(FakeDiscovery("Crossref", [PaperRecord("new", "New candidate")]),))
            )
            literature = Path(project_dir, "literature-set.md").read_text(encoding="utf-8")
            self.assertIn("Earlier candidate", literature)
            self.assertIn("New candidate", literature)

    def test_research_rerun_surfaces_and_preserves_direct_human_edit(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._research_ready_project(project_dir)
            orchestrator.run_research(
                ResearchConfig(discovery=(FakeDiscovery("OpenAlex", [PaperRecord("edit", "Editable candidate")]),))
            )
            evidence_path = Path(project_dir, "research-evidence.md")
            edited = evidence_path.read_text(encoding="utf-8").replace(
                "- edit: Editable candidate (OpenAlex);",
                "- edit: HUMAN CORRECTION - verify catalyst identity (OpenAlex);",
            )
            evidence_path.write_text(edited, encoding="utf-8")

            rerun = orchestrator.run_research(
                ResearchConfig(discovery=(FakeDiscovery("Crossref", [PaperRecord("new-edit", "New run")]),))
            )
            evidence = evidence_path.read_text(encoding="utf-8")
            self.assertEqual(rerun.status, "WAITING_FOR_HUMAN")
            self.assertEqual(rerun.human_action, "REQUIRED")
            self.assertIn("Preserved human edits and conflicts", evidence)
            self.assertIn("HUMAN CORRECTION - verify catalyst identity", evidence)

    def test_mineru_success_still_uses_grobid_as_structure_supplement(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._research_ready_project(project_dir)
            mineru = FakeParser("MinerU")
            grobid = FakeParser("GROBID")
            docling = FakeParser("Docling")
            orchestrator.run_research(
                ResearchConfig(
                    discovery=(FakeDiscovery("OpenAlex", [PaperRecord("p6", "Parsing paper")]),),
                    full_text=(FakeFullText("Unpaywall", "full text"),),
                    parsers=(docling, grobid, mineru),
                )
            )
            self.assertEqual(mineru.calls, ["p6"])
            self.assertEqual(grobid.calls, ["p6"])
            self.assertEqual(docling.calls, [])

    def test_docling_runs_when_grobid_supplement_fails(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._research_ready_project(project_dir)
            mineru = FakeParser("MinerU")
            grobid = FakeParser("GROBID", error=CapabilityUnavailable("structure failed"))
            docling = FakeParser("Docling")
            orchestrator.run_research(
                ResearchConfig(
                    discovery=(FakeDiscovery("OpenAlex", [PaperRecord("p6b", "Fallback parsing paper")]),),
                    full_text=(FakeFullText("Unpaywall", "full text"),),
                    parsers=(docling, grobid, mineru),
                )
            )
            self.assertEqual(mineru.calls, ["p6b"])
            self.assertEqual(grobid.calls, ["p6b"])
            self.assertEqual(docling.calls, ["p6b"])

    def test_parser_output_without_page_or_section_locator_is_degraded(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._research_ready_project(project_dir)
            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(FakeDiscovery("OpenAlex", [PaperRecord("p6c", "No locator paper")]),),
                    full_text=(FakeFullText("Unpaywall", "full text"),),
                    parsers=(FakeParser("MinerU", locators=()),),
                )
            )
            self.assertEqual(result.status, "READY_FOR_NEXT_PHASE")
            evidence = Path(project_dir, "research-evidence.md").read_text(encoding="utf-8")
            self.assertIn("no page/section locators", evidence)
            self.assertIn("structured parse: no", evidence)

    def test_local_pdf_placeholder_locator_is_not_treated_as_page_evidence(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._research_ready_project(project_dir)
            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(FakeDiscovery("OpenAlex", [PaperRecord("p6d", "Placeholder locator")]),),
                    full_text=(FakeFullText("Unpaywall", "full text"),),
                    parsers=(FakeParser("MinerU", locators=("paper.pdf#local-pdf",)),),
                )
            )
            evidence = Path(project_dir, "research-evidence.md").read_text(encoding="utf-8")
            self.assertEqual(result.assets["readiness"], "DISCOVERY_READY")
            self.assertIn("no page/section locators", evidence)

    def test_full_text_without_legal_access_basis_is_rejected(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._research_ready_project(project_dir)
            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(FakeDiscovery("OpenAlex", [PaperRecord("p7", "Access paper")]),),
                    full_text=(FakeFullText("Unknown mirror", "full text", access_basis="UNKNOWN"),),
                    parsers=(FakeParser("MinerU"),),
                )
            )
            evidence = Path(project_dir, "research-evidence.md").read_text(encoding="utf-8")
            self.assertEqual(result.status, "WAITING_FOR_HUMAN")
            self.assertEqual(result.human_action, "REQUIRED")
            self.assertIn("legal access basis", evidence)
            self.assertIn("structured parse: no", evidence)

    def test_later_legal_full_text_route_recovers_from_invalid_adapter(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._research_ready_project(project_dir)
            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(FakeDiscovery("OpenAlex", [PaperRecord("p8", "Legal fallback paper")]),),
                    full_text=(
                        FakeFullText("Unknown mirror", "untrusted", access_basis="UNKNOWN"),
                        FakeFullText("Unpaywall", "authorized text"),
                    ),
                    parsers=(FakeParser("MinerU"),),
                )
            )
            self.assertEqual(result.status, "READY_FOR_NEXT_PHASE")
            evidence = Path(project_dir, "research-evidence.md").read_text(encoding="utf-8")
            self.assertIn("structured parse: yes", evidence)

    def _research_ready_project(self, project_dir):
        orchestrator = ChemicalReviewOrchestrator(project_dir)
        orchestrator.start("nickel-catalyzed cross-coupling")
        orchestrator.continue_grill(
            {
                "core_claims": "Mechanism varies with ligand and substrate class.",
                "scope": "Nickel-catalyzed C-C coupling",
                "exclusions": "Palladium-only systems",
                "audience": "Organometallic chemists",
                "contribution": "Reconcile competing mechanistic models",
                "researcher_context": "No prior context beyond the stated nickel coupling scope.",
                "evidence_standards": "Primary papers with legal full-text page or section locators.",
                "boundary_scenarios": "Treat unmatched ligands, substrates, and locators as gaps.",
            }
        )
        orchestrator.confirm_current_intent()
        return orchestrator


if __name__ == "__main__":
    unittest.main()
