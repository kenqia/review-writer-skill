from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
V2_SKILLS = {
    "chemical-review-intent": ROOT / ".agents" / "skills" / "chemical-review-intent",
    "chemical-review-research": ROOT / ".agents" / "skills" / "chemical-review-research",
    "chemical-review-synthesis": ROOT / ".agents" / "skills" / "chemical-review-synthesis",
    "chemical-review-qa": ROOT / ".agents" / "skills" / "chemical-review-qa",
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class V2ProductTests(unittest.TestCase):
    def test_four_public_skills_have_explicit_boundaries_and_no_v1_entrypoint(self):
        for name, skill in V2_SKILLS.items():
            self.assertTrue((skill / "SKILL.md").is_file(), name)
            self.assertTrue((skill / "agents" / "openai.yaml").is_file(), name)
            self.assertNotIn("orchestrator", {p.name for p in skill.iterdir()})
        manifest = json.loads(
            (ROOT / "plugins" / "chemical-review" / ".codex-plugin" / "plugin.json").read_text()
        )
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(
            set(manifest["interface"]["capabilities"]),
            {"Interactive", "Research", "Write"},
        )

    def test_intent_topic_only_then_confirmed_change_requires_explicit_confirmation(self):
        intent = load_module("v2_intent_test", V2_SKILLS["chemical-review-intent"] / "intent.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            stage = intent.IntentStage(project)
            draft = stage.initialize("nickel-mediated C-C coupling")
            self.assertFalse(draft.confirmed)
            self.assertIn("Research question", (project / "review-brief.md").read_text())
            confirmed = stage.confirm(
                {
                    "research_question": "How do ligand effects change nickel-mediated C-C coupling?",
                    "core_claims": ["Ligand electronics change selectivity through mechanism-dependent effects."],
                    "scope": "Nickel catalytic C-C coupling in homogeneous systems, 2015-present.",
                    "exclusions": "No process economics or unrelated metals.",
                    "audience": "Synthetic chemistry researchers.",
                    "contribution": "A condition-aware comparison of ligand effects.",
                    "evidence_standards": "Original full text with page/section locators; metadata is discovery only.",
                    "boundary_scenarios": "Unknown and NOT_COMPARABLE are retained.",
                }
            )
            self.assertTrue(confirmed.confirmed)
            changed = stage.propose_change({"scope": "Only nickel-catalyzed cross-coupling, 2020-present."})
            self.assertFalse(changed.confirmed)
            self.assertTrue((project / "review-brief.proposed.md").is_file())
            with self.assertRaises(intent.ConfirmationRequired):
                stage.read_confirmed()
            stage.confirm_change()
            self.assertIn("2020-present", (project / "review-brief.md").read_text())

    def test_intent_reuses_only_explicit_project_material(self):
        intent = load_module("v2_intent_material_test", V2_SKILLS["chemical-review-intent"] / "intent.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            material = project / "project-context.md"
            material.write_text("Known scope: homogeneous nickel chemistry.", encoding="utf-8")
            (project / ".private.md").write_text("must not be copied", encoding="utf-8")
            intent.IntentStage(project).initialize("nickel coupling", materials=(material,))
            brief = (project / "review-brief.md").read_text(encoding="utf-8")
            self.assertIn("homogeneous nickel chemistry", brief)
            self.assertNotIn("must not be copied", brief)

    def test_research_waits_for_restricted_pdf_then_resumes_without_dropping_registry(self):
        research = load_module("v2_research_test", V2_SKILLS["chemical-review-research"] / "research.py")
        intent = load_module("v2_intent_for_research", V2_SKILLS["chemical-review-intent"] / "intent.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            intent.IntentStage(project).initialize("nickel coupling")
            intent.IntentStage(project).confirm(
                {
                    "research_question": "How do ligand effects alter nickel coupling?",
                    "core_claims": ["Ligand electronics alter selectivity."],
                    "scope": "Homogeneous nickel coupling.",
                    "exclusions": "Unrelated metals.",
                    "audience": "Chemists.",
                    "contribution": "Comparability-aware synthesis.",
                    "evidence_standards": "Original PDF and locators.",
                    "boundary_scenarios": "Retain UNKNOWN and Chemical GAP.",
                }
            )
            fixture_dir = project / "fixtures"
            fixture_dir.mkdir()
            (fixture_dir / "research.json").write_text(
                json.dumps(
                    {
                        "papers": [
                            {
                                "identifier": "doi:10.1234/example",
                                "doi": "10.1234/example",
                                "title": "A ligand effect example",
                                "year": 2024,
                                "full_text_url": "https://publisher.example/example.pdf",
                                "access_basis": "RESTRICTED",
                                "priority": "CORE",
                                "claim_relevance": "Ligand electronics alter selectivity.",
                            }
                        ],
                        "parsed": {
                            "doi:10.1234/example": {
                                "parser": "MinerU",
                                "sections": ["Results: ligand A gives 80% selectivity."],
                                "locators": ["example.pdf#page=2#section=Results"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            class Entity:
                name = "PubChem"

                def expand(self, term):
                    return ("nickelate",)

            first = research.ResearchStage(project).run(fixture_dir=fixture_dir, entity_adapters=[Entity()])
            self.assertEqual(first.status, "WAITING_FOR_USER")
            request_text = (project / "research" / "download-requests.md").read_text()
            self.assertIn("https://publisher.example/example.pdf", request_text)
            self.assertIn("authorized-pdfs", request_text)
            registry_before = (project / "research" / "source-registry.md").read_text()
            inbox = project / "research" / "inbox" / "authorized-pdfs"
            inbox.mkdir(parents=True, exist_ok=True)
            (inbox / "doi-10.1234-example.pdf").write_bytes(b"%PDF DOI 10.1234/example")
            second = research.ResearchStage(project).run(fixture_dir=fixture_dir, entity_adapters=[Entity()])
            self.assertEqual(second.status, "READY_FOR_SYNTHESIS")
            registry_after = (project / "research" / "source-registry.md").read_text()
            self.assertIn("doi:10.1234/example", registry_after)
            self.assertIn("example.pdf#page=2", registry_after)
            self.assertGreaterEqual(len(registry_after), len(registry_before))
            self.assertIn("MinerU", (project / "research" / "research-handoff.md").read_text())
            self.assertTrue((project / "research" / "provider-status.md").is_file())
            self.assertIn("nickelate", (project / "research" / "terms-and-entities.md").read_text())

    def test_provider_adapters_normalize_fixture_responses_and_never_persist_credentials(self):
        research = load_module("v2_provider_test", V2_SKILLS["chemical-review-research"] / "research.py")

        class Transport:
            def __init__(self, body):
                self.body = body

            def request(self, method, url, *, headers, body=None, timeout):
                return research.HttpResponse(200, {"content-type": "application/json"}, self.body)

        adapters = [
            research.OpenAlexAdapter(transport=Transport({"results": [{"id": "https://openalex.org/W1", "title": "A"}]})),
            research.SemanticScholarAdapter(transport=Transport({"data": [{"paperId": "S1", "title": "A"}]})),
            research.CrossrefAdapter(transport=Transport({"message": {"items": [{"DOI": "10.1/x", "title": ["A"]}]}})),
            research.PubChemAdapter(transport=Transport({"InformationList": {"Information": [{"CID": 1, "Synonym": ["A"]}]}})),
            research.ChebiAdapter(transport=Transport({"results": [{"chebiId": "CHEBI:1", "name": "A"}]})),
            research.UnpaywallAdapter(email="user@example.org", transport=Transport({"doi": "10.1/x", "best_oa_location": {"url_for_pdf": "https://oa.example/x.pdf"}})),
            research.EuropePmcAdapter(transport=Transport({"resultList": {"result": [{"pmcid": "PMC1", "title": "A"}]}})),
            research.CoreAdapter(api_key="configured-but-not-written", transport=Transport({"results": [{"id": "C1", "title": "A"}]})),
        ]
        outputs = [
            adapters[0].search("a"), adapters[1].search("a"), adapters[2].search("a"),
            adapters[3].expand("a"), adapters[4].expand("a"), adapters[5].locate("10.1/x"),
            adapters[6].locate("10.1/x"), adapters[7].locate("10.1/x"),
        ]
        self.assertTrue(all(outputs))
        self.assertNotIn("configured-but-not-written", repr(outputs))
        crossref = outputs[2][0]
        self.assertEqual(crossref.provider, "Crossref")
        self.assertEqual(crossref.authors, ())

    def test_provider_errors_are_redacted_before_status_is_persisted(self):
        research = load_module("v2_provider_redaction_test", V2_SKILLS["chemical-review-research"] / "research.py")

        class FailingTransport:
            def request(self, method, url, *, headers, body=None, timeout):
                raise RuntimeError("GET https://provider.invalid?api_key=SUPERSECRET")

        adapter = research.OpenAlexAdapter(api_key="SUPERSECRET", transport=FailingTransport())
        with self.assertRaises(research.ProviderUnavailable):
            adapter.search("a", limit=1)
        self.assertNotIn("SUPERSECRET", adapter.last_error)
        self.assertIn("[REDACTED]", adapter.last_error)

        class HeaderFailingTransport:
            def request(self, method, url, *, headers, body=None, timeout):
                raise RuntimeError("request failed with Authorization: Bearer DIRECTSECRET")

        direct_adapter = research.CoreAdapter(api_key="DIRECTSECRET", transport=HeaderFailingTransport())
        with self.assertRaises(research.ProviderUnavailable):
            direct_adapter.locate("10.1/x")
        self.assertNotIn("DIRECTSECRET", direct_adapter.last_error)
        self.assertIn("[REDACTED]", direct_adapter.last_error)

    def test_download_queue_is_evidence_selected_and_not_truncated_at_a_fixed_count(self):
        research = load_module("v2_priority_queue", V2_SKILLS["chemical-review-research"] / "research.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "review-brief.md").write_text("---\nconfirmed: true\n---\n\n## Topic\nQueue test\n", encoding="utf-8")
            fixture_dir = project / "fixtures"
            fixture_dir.mkdir()
            papers = [
                {
                    "identifier": f"doi:10.1234/core-{index}",
                    "doi": f"10.1234/core-{index}",
                    "title": f"Core paper {index}",
                    "full_text_url": f"https://publisher.example/core-{index}.pdf",
                    "access_basis": "RESTRICTED",
                    "priority": "CORE",
                    "claim_relevance": f"Core claim {index} cannot be assessed without this full text.",
                    "non_substitutability": "Unique reaction conditions and endpoint.",
                }
                for index in range(11)
            ]
            papers.append({
                "identifier": "doi:10.1234/background",
                "doi": "10.1234/background",
                "title": "Replaceable background",
                "full_text_url": "https://publisher.example/background.pdf",
                "access_basis": "RESTRICTED",
                "priority": "LOW",
                "claim_relevance": "",
            })
            (fixture_dir / "research.json").write_text(json.dumps({"papers": papers}), encoding="utf-8")
            result = research.ResearchStage(project).run(
                fixture_dir=fixture_dir,
                adapters=(),
                entity_adapters=(),
                full_text_adapters=(),
            )
            self.assertEqual(result.status, "WAITING_FOR_USER")
            requests = (project / "research" / "download-requests.md").read_text(encoding="utf-8")
            self.assertEqual(requests.count("## doi-10-1234-core-"), 11)
            self.assertIn("non_substitutability: Unique reaction conditions and endpoint.", requests)
            self.assertNotIn("doi:10.1234/background", requests)

    def test_configured_open_access_locator_is_downloaded_and_recorded_before_parse(self):
        research = load_module("v2_open_access_route", V2_SKILLS["chemical-review-research"] / "research.py")
        intent = load_module("v2_open_access_intent", V2_SKILLS["chemical-review-intent"] / "intent.py")

        class JsonTransport:
            def request(self, method, url, *, headers, body=None, timeout):
                return research.HttpResponse(200, {"content-type": "application/json"}, {"best_oa_location": {"url_for_pdf": "https://oa.example/core.pdf"}})

        class DownloadTransport:
            def request(self, method, url, *, headers, body=None, timeout):
                return research.HttpResponse(200, {"content-type": "application/pdf"}, b"%PDF authorized")

        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            intent.IntentStage(project).initialize("open access route")
            intent.IntentStage(project).confirm({
                "research_question": "Which route is legal?", "core_claims": ["Open access can be downloaded."],
                "scope": "One paper.", "exclusions": "None.", "audience": "Chemists.",
                "contribution": "Traceable route.", "evidence_standards": "PDF locator.", "boundary_scenarios": "UNKNOWN retained.",
            })
            fixture_dir = project / "fixtures"
            fixture_dir.mkdir()
            (fixture_dir / "research.json").write_text(json.dumps({
                "papers": [{"identifier": "doi:10.1234/oa", "doi": "10.1234/oa", "title": "OA paper", "claim_relevance": "Open route"}],
                "parsed": {"doi:10.1234/oa": {"parser": "MinerU", "sections": ["A result"], "locators": ["core.pdf#page=1"]}},
            }), encoding="utf-8")
            result = research.ResearchStage(project).run(
                fixture_dir=fixture_dir,
                full_text_adapters=[research.UnpaywallAdapter(email="reader@example.org", transport=JsonTransport())],
                download_transport=DownloadTransport(),
            )
            self.assertEqual(result.status, "READY_FOR_SYNTHESIS")
            registry = (project / "research" / "source-registry.md").read_text(encoding="utf-8")
            self.assertIn("https://oa.example/core.pdf", registry)
            self.assertEqual(len(list((project / "research" / "fulltext").glob("*.pdf"))), 1)

    def test_direct_download_failure_returns_a_user_route_and_rejects_html(self):
        research = load_module("v2_download_failure", V2_SKILLS["chemical-review-research"] / "research.py")

        class HtmlTransport:
            def request(self, method, url, *, headers, body=None, timeout):
                return research.HttpResponse(200, {"content-type": "text/html"}, b"<html>login</html>")

        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "paper.pdf"
            with self.assertRaises(research.ProviderUnavailable):
                research.ResearchStage(Path(temp))._download("https://oa.example/paper.pdf", target, transport=HtmlTransport())

    def test_mineru_timeout_degrades_to_pdftotext(self):
        research = load_module("v2_mineru_timeout", V2_SKILLS["chemical-review-research"] / "research.py")
        parser = research.MinerUParser(command="mineru --output markdown")
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "paper.pdf"
            pdf.write_bytes(b"%PDF fixture")
            with patch.object(research.subprocess, "run", side_effect=research.subprocess.TimeoutExpired("mineru", 180)):
                with self.assertRaises(research.ProviderUnavailable):
                    parser.parse(pdf, "doi:10.1/x")
            stage = research.ResearchStage(Path(temp))
            with patch.dict(os.environ, {"MINERU_COMMAND": "configured"}), patch.object(research.MinerUParser, "parse", side_effect=research.ProviderUnavailable("timeout")), patch.object(research, "_pdftotext", return_value=(("fallback",), ("paper.pdf#page=1",))):
                sections, locators, parser_name, note = stage._parse(pdf, "doi:10.1/x", None)
            self.assertEqual((sections, locators, parser_name), (("fallback",), ("paper.pdf#page=1",), "pdftotext"))
            self.assertIn("LOW_FIDELITY_FALLBACK", note)

    def test_unmatched_inbox_pdf_is_held_for_explicit_binding(self):
        research = load_module("v2_binding_research", V2_SKILLS["chemical-review-research"] / "research.py")
        intent = load_module("v2_binding_intent", V2_SKILLS["chemical-review-intent"] / "intent.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            stage = intent.IntentStage(project)
            stage.initialize("binding review")
            stage.confirm({
                "research_question": "Which paper is this?", "core_claims": ["Identity must be deterministic."],
                "scope": "One paper.", "exclusions": "None.", "audience": "Chemists.",
                "contribution": "No guessing.", "evidence_standards": "DOI and locator.", "boundary_scenarios": "UNKNOWN retained.",
            })
            fixture_dir = project / "fixtures"
            fixture_dir.mkdir()
            (fixture_dir / "research.json").write_text(json.dumps({"papers": [{"identifier": "doi:10.1234/bind", "doi": "10.1234/bind", "title": "Binding paper", "access_basis": "RESTRICTED", "full_text_url": "https://restricted.example/bind.pdf", "priority": "CORE", "claim_relevance": "Identity must be verified for the core claim."}]}), encoding="utf-8")
            first = research.ResearchStage(project).run(fixture_dir=fixture_dir)
            self.assertEqual(first.status, "WAITING_FOR_USER")
            inbox = project / "research" / "inbox" / "authorized-pdfs"
            (inbox / "unrelated-paper.pdf").write_bytes(b"pdf")
            second = research.ResearchStage(project).run(fixture_dir=fixture_dir)
            self.assertEqual(second.status, "WAITING_FOR_USER")
            self.assertTrue((project / "research" / "binding-requests.md").is_file())

    def test_synthesis_and_qa_keep_evidence_boundaries_and_conflicts(self):
        synthesis = load_module("v2_synthesis_test", V2_SKILLS["chemical-review-synthesis"] / "synthesis.py")
        qa = load_module("v2_qa_test", V2_SKILLS["chemical-review-qa"] / "qa.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "review-brief.md").write_text("---\nconfirmed: true\n---\n\n# Review Brief\n\n## Research question\nHow?\n", encoding="utf-8")
            research_dir = project / "research"
            research_dir.mkdir()
            (research_dir / "research-handoff.md").write_text("# Research Handoff\n\nResult: RESEARCH_GAP\n", encoding="utf-8")
            (research_dir / "evidence-notes.md").write_text("# Evidence Notes\n\n- VERIFIED_SOURCE_FACT [doi:10.1234/example @ example.pdf#page=2]: 80% selectivity.\n", encoding="utf-8")
            candidate = project / "candidate.md"
            candidate.write_text(
                "# Candidate\n\nStatus: unreviewed; evidence-bounded; partial-scope\n\n"
                "## Comparison\nSOURCE_FACT [doi:10.1234/example @ example.pdf#page=2]: 80% selectivity.\n"
                "\nMODEL_SYNTHESIS: The result is not comparable without matched conditions.\n"
                "\nMODEL_HYPOTHESIS: Electronics may change the rate-limiting step.\n"
                "\nChemical GAP: one core paper remains unavailable.\n"
                "\nUNKNOWN: temperature of the comparator.\nNOT_COMPARABLE: endpoints differ.\n",
                encoding="utf-8",
            )
            draft = synthesis.SynthesisStage(project).publish(candidate)
            self.assertEqual(draft.status, "UNREVIEWED_PARTIAL")
            self.assertTrue((project / "reader-draft.md").is_file())
            self.assertTrue((project / "research-draft.md").is_file())
            self.assertNotIn("SOURCE_FACT [", (project / "reader-draft.md").read_text(encoding="utf-8"))
            qa_stage = qa.QAStage(project)
            contexts = qa_stage.prepare()
            self.assertEqual(len(contexts), 4)
            for context in contexts:
                self.assertTrue((Path(context) / "context.md").is_file())
            reports = qa_stage.write_fixture_reports(
                {"evidence-locator": "cited locator: example.pdf#page=2\nseverity: HIGH\nrationale: locator conflict\nearliest return stage: Research", "chemistry-comparability": "cited locator: example.pdf#page=2\nseverity: HIGH\nrationale: conflict: LOW\nearliest return stage: Research", "synthesis-novelty": "cited locator: example.pdf#page=2\nseverity: MEDIUM\nrationale: bounded\nearliest return stage: Synthesis", "overclaim-counterexample": "cited locator: example.pdf#page=2\nseverity: HIGH\nrationale: bounded\nearliest return stage: Synthesis"}
            )
            qa_stage.finalize()
            self.assertEqual(len(reports), 4)
            self.assertTrue((project / "qa" / "review-report.md").is_file())
            self.assertIn("conflict", (project / "qa" / "review-report.md").read_text().lower())
            self.assertIn("Research", (project / "qa" / "revision-plan.md").read_text())

    def test_synthesis_rejects_source_fact_from_unverified_parser_excerpt(self):
        synthesis = load_module("v2_synthesis_boundary_test", V2_SKILLS["chemical-review-synthesis"] / "synthesis.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "review-brief.md").write_text("---\nconfirmed: true\n---\n\n# Review Brief\n", encoding="utf-8")
            research_dir = project / "research"
            research_dir.mkdir()
            (research_dir / "research-handoff.md").write_text("# Research Handoff\n\nResult: READY_FOR_SYNTHESIS\n", encoding="utf-8")
            (research_dir / "evidence-notes.md").write_text("SOURCE_EXCERPT [doi:10.1234/x @ paper.pdf#page=1]: excerpt\n", encoding="utf-8")
            with self.assertRaises(synthesis.EvidenceBoundaryError):
                synthesis.SynthesisStage(project).publish("SOURCE_FACT [doi:10.1234/x @ paper.pdf#page=1]: invented fact")

    def test_synthesis_rejects_unverified_source_fact_even_when_content_matches(self):
        synthesis = load_module("v2_synthesis_verification_marker", V2_SKILLS["chemical-review-synthesis"] / "synthesis.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "review-brief.md").write_text("---\nconfirmed: true\n---\n", encoding="utf-8")
            research_dir = project / "research"
            research_dir.mkdir()
            (research_dir / "research-handoff.md").write_text("Result: READY_FOR_SYNTHESIS\n", encoding="utf-8")
            (research_dir / "evidence-notes.md").write_text(
                "SOURCE_FACT [doi:10.1/x @ paper.pdf#page=1]: 80% selectivity.\n",
                encoding="utf-8",
            )
            with self.assertRaises(synthesis.EvidenceBoundaryError):
                synthesis.SynthesisStage(project).publish(
                    "SOURCE_FACT [doi:10.1/x @ paper.pdf#page=1]: 80% selectivity."
                )

    def test_synthesis_rejects_a_mismatched_fact_at_anotherwise_valid_locator(self):
        synthesis = load_module("v2_synthesis_claim_match", V2_SKILLS["chemical-review-synthesis"] / "synthesis.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "review-brief.md").write_text("---\nconfirmed: true\n---\n", encoding="utf-8")
            research_dir = project / "research"
            research_dir.mkdir()
            (research_dir / "research-handoff.md").write_text("Result: READY_FOR_SYNTHESIS\n", encoding="utf-8")
            (research_dir / "evidence-notes.md").write_text("VERIFIED_SOURCE_FACT [doi:10.1/x @ paper.pdf#page=1]: 80% selectivity.\n", encoding="utf-8")
            with self.assertRaises(synthesis.EvidenceBoundaryError):
                synthesis.SynthesisStage(project).publish("SOURCE_FACT [doi:10.1/x @ paper.pdf#page=1]: 90% selectivity.")

    def test_fresh_project_black_box_intent_research_synthesis_qa(self):
        intent = load_module("v2_e2e_intent", V2_SKILLS["chemical-review-intent"] / "intent.py")
        research = load_module("v2_e2e_research", V2_SKILLS["chemical-review-research"] / "research.py")
        synthesis = load_module("v2_e2e_synthesis", V2_SKILLS["chemical-review-synthesis"] / "synthesis.py")
        qa = load_module("v2_e2e_qa", V2_SKILLS["chemical-review-qa"] / "qa.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            i = intent.IntentStage(project)
            i.initialize("nickel ligand effects")
            i.confirm({
                "research_question": "How do ligand effects change nickel coupling selectivity?",
                "core_claims": ["Ligand electronics alter selectivity under mechanism-dependent conditions."],
                "scope": "Homogeneous nickel coupling, 2015-present.",
                "exclusions": "No unrelated metals or process economics.",
                "audience": "Synthetic chemists.",
                "contribution": "A condition-aware comparison.",
                "evidence_standards": "Original full text with page/section locators.",
                "boundary_scenarios": "Retain UNKNOWN, NOT_COMPARABLE, and Chemical GAP.",
            })
            fixture_dir = project / "fixtures"
            fixture_dir.mkdir()
            (fixture_dir / "research.json").write_text(json.dumps({
                "papers": [{
                    "identifier": "doi:10.1234/core", "doi": "10.1234/core", "title": "Core ligand study",
                    "full_text_url": "https://restricted.example/core.pdf", "access_basis": "RESTRICTED",
                    "priority": "CORE", "claim_relevance": "Ligand electronics alter selectivity.",
                }],
                "parsed": {"doi:10.1234/core": {"parser": "MinerU", "sections": ["Results: ligand A gives 80% selectivity."], "locators": ["core.pdf#page=2#section=Results"]}},
            }), encoding="utf-8")
            waiting = research.ResearchStage(project).run(fixture_dir=fixture_dir)
            self.assertEqual(waiting.status, "WAITING_FOR_USER")
            inbox = project / "research" / "inbox" / "authorized-pdfs"
            (inbox / "doi-10.1234-core.pdf").write_bytes(b"authorized fixture")
            ready = research.ResearchStage(project).run(fixture_dir=fixture_dir)
            self.assertEqual(ready.status, "READY_FOR_SYNTHESIS")
            evidence_notes = project / "research" / "evidence-notes.md"
            evidence_notes.write_text(evidence_notes.read_text(encoding="utf-8") + "\n- VERIFIED_SOURCE_FACT [doi:10.1234/core @ core.pdf#page=2#section=Results]: 80% selectivity after original PDF check.\n", encoding="utf-8")
            candidate = project / "candidate.md"
            candidate.write_text(
                "# Candidate\n\nStatus: unreviewed; evidence-bounded\n\n"
                "SOURCE_FACT [doi:10.1234/core @ core.pdf#page=2#section=Results]: 80% selectivity.\n\n"
                "MODEL_SYNTHESIS: The result needs matched conditions before comparison.\n\n"
                "MODEL_HYPOTHESIS: Electronics may alter the rate-limiting step.\n\n"
                "UNKNOWN: comparator temperature.\nNOT_COMPARABLE: endpoints differ.\n",
                encoding="utf-8",
            )
            draft = synthesis.SynthesisStage(project).publish(candidate)
            self.assertEqual(draft.status, "UNREVIEWED")
            qa_stage = qa.QAStage(project)
            contexts = qa_stage.prepare()
            self.assertEqual(len(contexts), 4)
            qa_stage.write_fixture_reports({slug: "cited locator: core.pdf#page=2\nseverity: LOW\nearliest return stage: Synthesis\nrationale: bounded" for slug, _label, _instruction in qa.ROLES})
            final = qa_stage.finalize()
            self.assertTrue(final.report_path.is_file())
            self.assertTrue((project / "review-brief.md").is_file())
            self.assertTrue((project / "research" / "source-registry.md").is_file())
            self.assertTrue((project / "draft.md").is_file())


if __name__ == "__main__":
    unittest.main()
