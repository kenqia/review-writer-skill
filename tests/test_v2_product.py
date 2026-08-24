from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
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

    def test_research_preflight_stops_for_missing_configuration_until_choice(self):
        research = load_module("v2_research_preflight_test", V2_SKILLS["chemical-review-research"] / "research.py")
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            project = Path(temp)
            (project / "review-brief.md").write_text("---\nconfirmed: true\n---\n\n## Topic\nPreflight test\n", encoding="utf-8")
            stage = research.ResearchStage(project)
            with self.assertRaisesRegex(RuntimeError, "configuration choice"):
                stage.run()
            report = (project / "research" / "configuration-preflight.md").read_text(encoding="utf-8")
            self.assertIn("Decision: PENDING", report)
            self.assertIn("accept_degraded", report)
            self.assertIn("MinerU", report)

            with self.assertRaisesRegex(RuntimeError, "paused"):
                stage.run(config_choice="pause")
            self.assertIn("Decision: PAUSED", (project / "research" / "configuration-preflight.md").read_text(encoding="utf-8"))

            with self.assertRaisesRegex(RuntimeError, "configuration choice"):
                stage.run(config_choice="accept_degraded")
            self.assertIn("Decision: PENDING", (project / "research" / "configuration-preflight.md").read_text(encoding="utf-8"))

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
        self.assertNotIn("URLSIG", research._safe_error("GET https://provider.invalid/paper.pdf?X-Amz-Signature=URLSIG"))
        self.assertNotIn("URLUSER", research._safe_error("GET https://URLUSER:URLPASS@provider.invalid/paper.pdf"))
        self.assertNotIn("ENCUSERPASS", research._safe_error("GET https://user%40name:ENCUSERPASS@provider.invalid/paper.pdf"))
        self.assertNotIn("NESTEDSIG", research._safe_error("GET https://provider.invalid/redirect?next=https%3A%2F%2Fpublisher.example%2Fpaper.pdf%3Fsig%3DNESTEDSIG"))
        self.assertNotIn("DOUBLEENCODED", research._safe_error("GET https://provider.invalid/redirect?next=https%253A%252F%252Fpublisher.example%252Fpaper.pdf%253Fsig%253DDOUBLEENCODED"))
        self.assertNotIn("ENCUSER", research._safe_error("GET https%3A%2F%2FENCUSER%3AENCPASS%40provider.invalid%2Fpaper.pdf"))
        self.assertNotIn("HTTPSECRET", research._safe_error("GET https://provider.invalid/paper.pdf?download=1;sig=HTTPSECRET"))
        self.assertNotIn("AWSSECRET", research._safe_error("GET https://provider.invalid/paper.pdf?aws_access_key_id=AWSSECRET"))
        self.assertNotIn("AWSHYPHENSECRET", research._safe_error("GET https://provider.invalid/paper.pdf?aws-access-key-id=AWSHYPHENSECRET"))
        self.assertNotIn("ACCESSSECRET", research._safe_error("GET https://provider.invalid/paper.pdf?accessKey=ACCESSSECRET"))
        self.assertNotIn("XAPISECRET", research._safe_error("GET https://provider.invalid/paper.pdf?x-api-key=XAPISECRET"))
        self.assertNotIn("AMZSECRET", research._safe_error("GET https://provider.invalid/paper.pdf?x-amz-securitytoken=AMZSECRET"))
        self.assertNotIn("AUTHSECRET", research._safe_error("GET https://provider.invalid/paper.pdf?authToken=AUTHSECRET"))
        self.assertNotIn("FOOTOKENSECRET", research._safe_error("GET https://provider.invalid/paper.pdf?foo-token=FOOTOKENSECRET"))
        self.assertNotIn("BASICSECRET", research._safe_error("request failed with Authorization: Basic BASICSECRET"))

        class HttpErrorTransport:
            def request(self, method, url, *, headers, body=None, timeout):
                return research.HttpResponse(503, {"content-type": "application/json"}, {"error": "temporary"})

        http_adapter = research.OpenAlexAdapter(transport=HttpErrorTransport())
        with self.assertRaises(research.ProviderUnavailable):
            http_adapter.search("a", limit=1)
        self.assertIn("HTTP 503", http_adapter.last_error)

        class MalformedTransport:
            def request(self, method, url, *, headers, body=None, timeout):
                return research.HttpResponse(200, {"content-type": "application/json"}, b"not-json")

        malformed_adapter = research.OpenAlexAdapter(transport=MalformedTransport())
        with self.assertRaises(research.ProviderUnavailable):
            malformed_adapter.search("a", limit=1)
        self.assertIn("malformed JSON", malformed_adapter.last_error)

        class FailingEntity:
            name = "Fixture entity"

            def expand(self, term):
                raise research.ProviderUnavailable("GET https://entity.invalid?token=ENTITYSECRET")

        _, entity_failures = research.ResearchStage._expand_entities("## Topic\nEntity test\n", (FailingEntity(),))
        self.assertNotIn("ENTITYSECRET", " ".join(entity_failures))
        self.assertEqual(
            research._persisted_url("https://oa.example/paper.pdf?access_token=URLSECRET&download=1"),
            "",
        )
        self.assertEqual(
            research._persisted_url("https://oa.example/paper.pdf?X-Amz-Security-Token=URLSECRET"),
            "",
        )
        self.assertEqual(
            research._persisted_url("https://user:URLSECRET@oa.example/paper.pdf"),
            "",
        )
        self.assertEqual(
            research._persisted_url("https://oa.example/paper.pdf?bearer=URLSECRET"),
            "",
        )
        self.assertEqual(
            research._persisted_url("https://oa.example/paper.pdf?download=1;sig=URLSECRET"),
            "",
        )
        self.assertEqual(
            research._persisted_url("https://oa.example/paper.pdf#sig:URLSECRET"),
            "",
        )
        self.assertEqual(
            research._persisted_url("https://oa.example/paper.pdf?aws_access_key_id=URLSECRET"),
            "",
        )
        self.assertEqual(research._persisted_url("relative/paper.pdf"), "")
        self.assertEqual(research._url_status("relative/paper.pdf"), "INVALID_URL")
        self.assertEqual(
            research._persisted_url("https://oa.example/redirect?next=https%2525252525253A%2525252525252F%2525252525252Fpublisher.example%2525252525252Fpaper.pdf%2525252525253Fsig%2525252525253DDEEPSECRET"),
            "",
        )

    def test_provider_status_scrubs_injected_adapter_errors(self):
        research = load_module("v2_provider_status_scrub", V2_SKILLS["chemical-review-research"] / "research.py")

        class LeakyAdapter:
            name = "OpenAlex"
            last_error = "GET https://provider.invalid/paper.pdf?authToken=INJECTEDSECRET"

        with tempfile.TemporaryDirectory() as temp:
            stage = research.ResearchStage(Path(temp))
            stage._ensure_dirs()
            stage._write_provider_status((LeakyAdapter(),), ())
            status = (Path(temp) / "research" / "provider-status.md").read_text(encoding="utf-8")
            self.assertNotIn("INJECTEDSECRET", status)
        self.assertEqual(
            research._persisted_url("https://oa.example/redirect?next=https%3A%2F%2Fpublisher.example%2Fpaper.pdf%3Ftoken%3DURLSECRET"),
            "",
        )
        self.assertEqual(
            research._persisted_url("https://oa.example/paper.pdf?download=1"),
            "https://oa.example/paper.pdf?download=1",
        )

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

    def test_provider_discovery_marks_candidate_claim_relevance_for_restricted_full_text(self):
        research = load_module("v2_discovery_claim_relevance", V2_SKILLS["chemical-review-research"] / "research.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "review-brief.md").write_text(
                "---\nconfirmed: true\n---\n\n## Topic\nNickel coupling\n\n## Core-claim candidates\n- Ligand electronics alter selectivity.\n",
                encoding="utf-8",
            )

            class Discovery:
                name = "Fixture discovery"

                def search(self, query, limit=5):
                    return (research.Paper("doi:10.1234/discovered", "Discovered core paper", "10.1234/discovered", 2024, provider=self.name),)

            class Locator:
                name = "Fixture locator"

                def locate(self, doi):
                    return (research.FullTextLocation("doi:" + doi, "https://publisher.example/discovered.pdf", "RESTRICTED", self.name, False),)

            result = research.ResearchStage(project).run(
                adapters=(Discovery(),),
                entity_adapters=(),
                full_text_adapters=(Locator(),),
            )
            self.assertEqual(result.status, "WAITING_FOR_USER")
            requests = (project / "research" / "download-requests.md").read_text(encoding="utf-8")
            self.assertIn("https://publisher.example/discovered.pdf", requests)
            self.assertIn("Ligand electronics alter selectivity.", requests)
            self.assertIn("screening still required", requests)

    def test_relevant_title_without_claim_binding_is_not_auto_queued(self):
        research = load_module("v2_claim_binding_screen", V2_SKILLS["chemical-review-research"] / "research.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "review-brief.md").write_text("---\nconfirmed: true\n---\n\nTopic: nickel coupling\n", encoding="utf-8")
            fixture_dir = project / "fixtures"
            fixture_dir.mkdir()
            (fixture_dir / "research.json").write_text(json.dumps({"papers": [{"identifier": "doi:10.1/unbound", "doi": "10.1/unbound", "title": "Nickel coupling chemistry", "abstract": "Nickel coupling chemistry", "year": 2024, "full_text_url": "https://oa.example/unbound.pdf", "full_text_direct": True, "access_basis": "OPEN_ACCESS"}]}), encoding="utf-8")
            result = research.ResearchStage(project).run(fixture_dir=fixture_dir)
            self.assertEqual(result.status, "RESEARCH_GAP")
            manifest = json.loads((project / "research" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["coverage"]["included"], 0)
            self.assertEqual(manifest["coverage"]["manual_queue"], 0)

    def test_unrelated_explicit_claim_binding_is_excluded_even_when_title_is_chemistry(self):
        research = load_module("v2_unrelated_claim_binding", V2_SKILLS["chemical-review-research"] / "research.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "review-brief.md").write_text(
                "---\nconfirmed: true\n---\n\nTopic: nickel coupling\n\n## Core-claim candidates\n- Ligand electronics alter selectivity.\n",
                encoding="utf-8",
            )
            fixture_dir = project / "fixtures"
            fixture_dir.mkdir()
            (fixture_dir / "research.json").write_text(json.dumps({"papers": [{
                "identifier": "doi:10.1/unrelated", "doi": "10.1/unrelated",
                "title": "Nickel coupling chemistry", "abstract": "Nickel coupling chemistry",
                "claim_relevance": "Quantum computing unrelated claim.",
                "full_text_url": "https://oa.example/unrelated.pdf", "full_text_direct": True,
                "access_basis": "OPEN_ACCESS",
            }]}), encoding="utf-8")
            result = research.ResearchStage(project).run(fixture_dir=fixture_dir)
            manifest = json.loads((project / "research" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(result.status, "RESEARCH_GAP")
            self.assertEqual(manifest["coverage"]["included"], 0)
            self.assertEqual(manifest["coverage"]["manual_queue"], 0)

    def test_credential_bearing_full_text_url_is_withheld_with_visible_recovery_action(self):
        research = load_module("v2_signed_url_route", V2_SKILLS["chemical-review-research"] / "research.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "review-brief.md").write_text(
                "---\nconfirmed: true\n---\n\n## Topic\nSigned URL test\n",
                encoding="utf-8",
            )
            fixture_dir = project / "fixtures"
            fixture_dir.mkdir()
            (fixture_dir / "research.json").write_text(json.dumps({"papers": [{
                "identifier": "doi:10.1234/signed",
                "doi": "10.1234/signed",
                "title": "Signed route",
                "full_text_url": "https://publisher.example/paper.pdf?X-Amz-Security-Token=URLSECRET",
                "full_text_direct": False,
                "access_basis": "RESTRICTED",
                "priority": "CORE",
                "claim_relevance": "The core endpoint depends on this paper.",
            }]}), encoding="utf-8")
            result = research.ResearchStage(project).run(
                fixture_dir=fixture_dir,
                adapters=(),
                entity_adapters=(),
                full_text_adapters=(),
            )
            self.assertEqual(result.status, "WAITING_FOR_USER")
            request_text = (project / "research" / "download-requests.md").read_text(encoding="utf-8")
            handoff_text = (project / "research" / "research-handoff.md").read_text(encoding="utf-8")
            registry_text = (project / "research" / "source-registry.md").read_text(encoding="utf-8")
            manifest_text = (project / "research" / "manifest.json").read_text(encoding="utf-8")
            self.assertIn("WITHHELD_CREDENTIAL_BEARING_URL", request_text)
            self.assertIn("fresh legal landing/download URL without embedded credentials", request_text)
            self.assertIn("WITHHELD_CREDENTIAL_BEARING_URL", registry_text)
            self.assertNotIn("URLSECRET", request_text + handoff_text + registry_text)
            self.assertNotIn("URLSECRET", manifest_text)

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

    def test_credential_bearing_direct_open_access_url_is_not_requested_or_persisted(self):
        research = load_module("v2_direct_signed_url", V2_SKILLS["chemical-review-research"] / "research.py")

        class FailingDownloadTransport:
            def __init__(self):
                self.urls = []

            def request(self, method, url, *, headers, body=None, timeout):
                self.urls.append(url)
                raise AssertionError("credential-bearing URL must not reach the download transport")

        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "review-brief.md").write_text("---\nconfirmed: true\n---\n\n## Topic\nDirect signed route\n", encoding="utf-8")
            fixture_dir = project / "fixtures"
            fixture_dir.mkdir()
            (fixture_dir / "research.json").write_text(json.dumps({"papers": [{
                "identifier": "doi:10.1234/direct-signed",
                "doi": "10.1234/direct-signed",
                "title": "Direct signed route",
                "full_text_url": "https://publisher.example/paper.pdf?bearer=URLSECRET",
                "full_text_direct": True,
                "access_basis": "OPEN_ACCESS",
                "priority": "CORE",
                "claim_relevance": "The core endpoint depends on this paper.",
            }]}), encoding="utf-8")
            transport = FailingDownloadTransport()
            result = research.ResearchStage(project).run(
                fixture_dir=fixture_dir,
                adapters=(),
                entity_adapters=(),
                full_text_adapters=(),
                download_transport=transport,
            )
            self.assertEqual(result.status, "WAITING_FOR_USER")
            self.assertEqual(transport.urls, [])
            output = "".join((project / "research" / name).read_text(encoding="utf-8") for name in ("download-requests.md", "research-handoff.md", "source-registry.md"))
            self.assertIn("WITHHELD_CREDENTIAL_BEARING_URL", output)
            self.assertIn("fresh legal landing/download URL without embedded credentials", output)
            self.assertNotIn("URLSECRET", output)

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

    def test_research_extracts_intent_topic_and_builds_compact_provider_queries(self):
        research = load_module("v2_topic_query_contract", V2_SKILLS["chemical-review-research"] / "research.py")
        intent = load_module("v2_topic_query_intent", V2_SKILLS["chemical-review-intent"] / "intent.py")

        class RecordingAdapter:
            def __init__(self):
                self.name = "Recorder"
                self.queries = []

            def search(self, query, limit=5):
                self.queries.append(query)
                return ()

        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            stage = intent.IntentStage(project)
            stage.initialize("生成式 AI 分子发现｜Generative AI for Small-Molecule Discovery")
            stage.confirm({
                "research_question": "Which generative AI studies experimentally validate new small molecules?",
                "core_claims": ["Experimental validation must report attempted and confirmed molecules."],
                "scope": "Peer-reviewed small-molecule chemistry studies since 2020.",
                "exclusions": "No protein design.",
                "audience": "Chemists.",
                "contribution": "Evidence audit.",
                "evidence_standards": "Original full text and locators.",
                "boundary_scenarios": "Retain UNKNOWN and Chemical GAP.",
            })
            brief = (project / "review-brief.md").read_text(encoding="utf-8")
            self.assertEqual(research._brief_topic(brief), "生成式 AI 分子发现｜Generative AI for Small-Molecule Discovery")
            adapter = RecordingAdapter()
            research.ResearchStage(project)._discover(brief, {}, (adapter,), terms=("small molecule",))

        self.assertTrue(adapter.queries)
        self.assertTrue(any("small molecule" in query.lower() for query in adapter.queries))
        self.assertTrue(all("Which generative AI studies" not in query for query in adapter.queries))
        self.assertTrue(all("core claims:" not in query for query in adapter.queries))
        self.assertTrue(all(len(query) <= 220 for query in adapter.queries))

    def test_entity_expansion_uses_short_chemical_candidates_not_the_full_question(self):
        research = load_module("v2_entity_query_contract", V2_SKILLS["chemical-review-research"] / "research.py")

        class RecordingEntity:
            name = "PubChem"

            def __init__(self):
                self.terms = []

            def expand(self, term):
                self.terms.append(term)
                return ("molecule synonym",)

        brief = (
            "---\n"
            "topic: Generative AI for Small-Molecule Discovery\n"
            "confirmed: true\n"
            "---\n\n"
            "# Review Brief\n\n"
            "Topic: Generative AI for Small-Molecule Discovery\n\n"
            "## Research question\n"
            "Which generative AI studies experimentally validate new small molecules?\n\n"
            "## Core-claim candidates\n"
            "- Experimental validation must report attempted and confirmed molecules.\n"
        )
        adapter = RecordingEntity()
        terms, failures = research.ResearchStage._expand_entities(brief, (adapter,))

        self.assertFalse(failures)
        self.assertTrue(adapter.terms)
        self.assertTrue(all(len(term) <= 80 for term in adapter.terms))
        self.assertTrue(all("Which generative AI studies" not in term for term in adapter.terms))
        self.assertTrue(any("small molecule" in term.lower() for term in adapter.terms))
        self.assertIn("molecule synonym", terms)

    def test_mineru_command_receives_input_dir_for_a_single_pdf(self):
        research = load_module("v2_mineru_input_dir_contract", V2_SKILLS["chemical-review-research"] / "research.py")
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            return research.subprocess.CompletedProcess(command, 0, stdout="parsed markdown", stderr="")

        with tempfile.TemporaryDirectory() as temp, patch.object(research.subprocess, "run", side_effect=fake_run):
            pdf = Path(temp) / "paper.pdf"
            pdf.write_bytes(b"%PDF fixture")
            sections, _locators, _note = research.MinerUParser(command="mineru --output markdown").parse(pdf, "doi:10.1/x")

        self.assertEqual(sections, ("parsed markdown",))
        self.assertEqual(len(calls), 1)
        self.assertIn("--input-dir", calls[0])
        self.assertIn(str(pdf.parent), calls[0])

    def test_mineru_prefers_structured_markdown_over_batch_progress_logs(self):
        research = load_module("v2_mineru_markdown_output_contract", V2_SKILLS["chemical-review-research"] / "research.py")

        def fake_run(command, **kwargs):
            output_dir = Path(command[command.index("--output-dir") + 1])
            markdown = output_dir / "markdown"
            markdown.mkdir(parents=True)
            (markdown / "paper.md").write_text("# Parsed paper\n\nResults", encoding="utf-8")
            return research.subprocess.CompletedProcess(command, 0, stdout="[upload] paper.pdf\n[poll] done", stderr="")

        with tempfile.TemporaryDirectory() as temp, patch.object(research.subprocess, "run", side_effect=fake_run):
            pdf = Path(temp) / "paper.pdf"
            pdf.write_bytes(b"%PDF fixture")
            sections, _locators, _note = research.MinerUParser(command="mineru").parse(pdf, "doi:10.1/x")

        self.assertEqual(sections, ("# Parsed paper\n\nResults",))

    def test_mineru_progress_only_stdout_is_not_structured_success(self):
        research = load_module("v2_mineru_progress_only", V2_SKILLS["chemical-review-research"] / "research.py")

        def fake_run(command, **kwargs):
            return research.subprocess.CompletedProcess(command, 0, stdout="[upload] paper.pdf\n[poll] done", stderr="")

        with tempfile.TemporaryDirectory() as temp, patch.object(research.subprocess, "run", side_effect=fake_run):
            pdf = Path(temp) / "paper.pdf"
            pdf.write_bytes(b"%PDF fixture")
            with self.assertRaises(research.ProviderUnavailable):
                research.MinerUParser(command="mineru").parse(pdf, "doi:10.1/x")

    def test_mineru_keeps_single_pdf_wrapper_compatibility_after_batch_attempt(self):
        research = load_module("v2_mineru_wrapper_compatibility", V2_SKILLS["chemical-review-research"] / "research.py")
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if "--input-dir" in command:
                return research.subprocess.CompletedProcess(command, 2, stdout="", stderr="wrapper expects a PDF path")
            return research.subprocess.CompletedProcess(command, 0, stdout="wrapped markdown", stderr="")

        with tempfile.TemporaryDirectory() as temp, patch.object(research.subprocess, "run", side_effect=fake_run):
            pdf = Path(temp) / "paper.pdf"
            pdf.write_bytes(b"%PDF fixture")
            sections, _locators, _note = research.MinerUParser(command="mineru-wrapper").parse(pdf, "doi:10.1/x")

        self.assertEqual(sections, ("wrapped markdown",))
        self.assertEqual(len(calls), 2)
        self.assertIn("--input-dir", calls[0])
        self.assertEqual(calls[1][-1], str(pdf))

    def test_mineru_preflight_is_not_ready_without_a_real_pdf_probe(self):
        research = load_module("v2_mineru_preflight_contract", V2_SKILLS["chemical-review-research"] / "research.py")
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"MINERU_COMMAND": "mineru"}, clear=True):
            rows = research.ResearchStage(Path(temp))._configuration_rows()

        mineru = next(row for row in rows if row["capability"] == "Primary PDF parser (MinerU)")
        self.assertEqual(mineru["status"], "NOT_VERIFIED")

    def test_mineru_preflight_runs_a_real_pdf_probe_before_ready(self):
        research = load_module("v2_mineru_preflight_probe", V2_SKILLS["chemical-review-research"] / "research.py")
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"MINERU_COMMAND": "mineru"}, clear=True):
            project = Path(temp)
            inbox = project / "research" / "inbox" / "authorized-pdfs"
            inbox.mkdir(parents=True)
            pdf = inbox / "authorized.pdf"
            pdf.write_bytes(b"%PDF fixture")
            with patch.object(research.MinerUParser, "parse", return_value=(("parsed",), ("authorized.pdf#page=1",), "probe")) as parse:
                rows = research.ResearchStage(project)._configuration_rows()

        mineru = next(row for row in rows if row["capability"] == "Primary PDF parser (MinerU)")
        self.assertEqual(mineru["status"], "READY")
        parse.assert_called_once()
        self.assertEqual(parse.call_args.args[0], pdf)

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

    def test_research_manifest_screens_candidates_and_projects_four_layer_evidence(self):
        research = load_module("v2_manifest_screening", V2_SKILLS["chemical-review-research"] / "research.py")
        intent = load_module("v2_manifest_intent", V2_SKILLS["chemical-review-intent"] / "intent.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            stage = intent.IntentStage(project)
            stage.initialize("Generative AI for Small-Molecule Discovery")
            stage.confirm({
                "research_question": "Which generative AI studies experimentally validate new small molecules?",
                "core_claims": ["Experimental validation must report attempted and confirmed molecules."],
                "scope": "Peer-reviewed small-molecule chemistry studies since 2020.",
                "exclusions": "No protein design, reviews or workshop papers.",
                "audience": "Chemists.", "contribution": "Evidence audit.",
                "evidence_standards": "Original full text and locators.",
                "boundary_scenarios": "Retain UNKNOWN, NOT_COMPARABLE and Chemical GAP.",
            })
            fixture_dir = project / "fixtures"
            fixture_dir.mkdir()
            (fixture_dir / "research.json").write_text(json.dumps({
                "papers": [
                    {"identifier": "doi:10.1000/core", "doi": "10.1000/core", "title": "Generative AI for small-molecule discovery", "abstract": "We generate and experimentally validate novel small molecules.", "year": 2024, "publication_type": "journal-article", "full_text_url": "https://oa.example/core.pdf", "full_text_direct": True, "access_basis": "OPEN_ACCESS", "priority": "CORE", "claim_relevance": "Experimental validation must report attempted and confirmed molecules."},
                    {"identifier": "doi:10.1000/core-v2", "doi": "10.1000/core", "title": "Generative AI for small-molecule discovery (version)", "abstract": "duplicate version", "year": 2024, "publication_type": "journal-article", "provider": "second", "claim_relevance": "duplicate"},
                    {"identifier": "doi:10.1000/protein", "doi": "10.1000/protein", "title": "Generative AI for protein design", "abstract": "protein sequences only", "year": 2024, "publication_type": "journal-article", "full_text_url": "https://oa.example/protein.pdf", "full_text_direct": True, "access_basis": "OPEN_ACCESS", "priority": "CORE"},
                    {"identifier": "doi:10.1000/review", "doi": "10.1000/review", "title": "A review of molecular discovery", "abstract": "survey", "year": 2024, "publication_type": "review", "full_text_url": "https://oa.example/review.pdf", "full_text_direct": True, "access_basis": "OPEN_ACCESS", "priority": "CORE", "claim_relevance": "context"},
                    {"identifier": "doi:10.1000/old", "doi": "10.1000/old", "title": "Small molecule discovery before the range", "abstract": "old chemistry", "year": 2010, "publication_type": "journal-article", "claim_relevance": "out of range"},
                ],
                "parsed": {"doi:10.1000/core": {"parser": "MinerU", "sections": ["Results: 12 attempted molecules; 4 confirmed by NMR. Limitation: assay scope was narrow."], "locators": ["core.pdf#page=3#section=Results"]}},
            }), encoding="utf-8")

            class Download:
                def request(self, method, url, *, headers, body=None, timeout):
                    return research.HttpResponse(200, {"content-type": "application/pdf"}, b"%PDF core")

            result = research.ResearchStage(project).run(fixture_dir=fixture_dir, download_transport=Download())
            self.assertEqual(result.status, "READY_FOR_SYNTHESIS")
            manifest = json.loads((project / "research" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["brief_revision"], 2)
            self.assertEqual(manifest["coverage"]["raw_hits"], 5)
            self.assertEqual(manifest["coverage"]["unique_candidates"], 4)
            decisions = {row["identifier"]: row["screening"]["decision"] for row in manifest["candidates"]}
            self.assertEqual(decisions["doi:10.1000/core"], "INCLUDE")
            self.assertEqual(decisions["doi:10.1000/protein"], "EXCLUDE")
            self.assertEqual(decisions["doi:10.1000/review"], "EXCLUDE")
            self.assertEqual(decisions["doi:10.1000/old"], "EXCLUDE")
            self.assertEqual(manifest["coverage"]["downloaded_pdfs"], 1)
            self.assertEqual(manifest["coverage"]["mineru_success"], 1)
            self.assertIn("research_kernel", manifest["evidence_matrix"]["layers"])
            self.assertIn("SOURCE_FACT", manifest["evidence_matrix"]["claim_vocabulary"])
            self.assertIn("candidate_denominator", manifest["evidence_matrix"]["review_specific_fields"])
            evidence = manifest["sources"][0]["evidence_fields"]
            self.assertEqual(evidence["evidence_level"], "EXCERPT")
            self.assertEqual(evidence["candidate_denominator"], "12")
            self.assertEqual(evidence["identity_confirmation"], "4 confirmed by NMR")
            handoff = (project / "research" / "research-handoff.md").read_text(encoding="utf-8")
            self.assertIn("Raw hits: 5", handoff)
            self.assertIn("Excluded: 3", handoff)
            self.assertIn("Evidence-ready: 1", handoff)
            self.assertTrue((project / "research" / "evidence-matrix.md").is_file())
            self.assertNotIn("protein.pdf", (project / "research" / "download-requests.md").read_text(encoding="utf-8"))

    def test_research_optional_capabilities_do_not_block_and_provider_states_are_real(self):
        research = load_module("v2_capability_states", V2_SKILLS["chemical-review-research"] / "research.py")
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"CHEMICAL_REVIEW_ENABLE_NETWORK": "1", "UNPAYWALL_EMAIL": "", "CORE_API_KEY": ""}, clear=True):
            project = Path(temp)
            (project / "review-brief.md").write_text("---\nconfirmed: true\nrevision: 1\n---\n\nTopic: chemistry\n", encoding="utf-8")
            class Discovery:
                name = "Fixture discovery"
                last_status = "USABLE_RESULTS"
                last_error = ""
                def search(self, query, limit=5):
                    return ()
            parser = research.MinerUParser(command="mineru")
            with patch.object(research.ResearchStage, "_mineru_probe", return_value=("READY", "fixture probe")):
                rows = research.ResearchStage(project)._configuration_rows(discovery_adapters=(Discovery(),), parser=parser)
            by_name = {row["capability"]: row for row in rows}
            self.assertEqual(by_name["Additional open-access full text (Unpaywall)"]["status"], "OPTIONAL_MISSING")
            self.assertEqual(by_name["Additional repository full text (CORE)"]["status"], "OPTIONAL_MISSING")
            self.assertTrue(all(row["status"] != "MISSING" for row in rows if row["status"] == "OPTIONAL_MISSING"))
            self.assertIn(by_name["Metadata discovery (OpenAlex / Semantic Scholar / Crossref)"]["status"], {"REACHABLE", "USABLE_RESULTS"})
            self.assertEqual(by_name["Chemistry term expansion (PubChem / ChEBI)"]["status"], "CONFIGURED")

    def test_verified_evidence_promotion_updates_manifest_and_evidence_handoff(self):
        research = load_module("v2_verified_evidence_promotion", V2_SKILLS["chemical-review-research"] / "research.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "review-brief.md").write_text("---\nconfirmed: true\nrevision: 1\n---\n\nTopic: molecular discovery\n", encoding="utf-8")
            stage = research.ResearchStage(project)
            stage._ensure_dirs()
            pdf = project / "research" / "fulltext" / "paper.pdf"
            pdf.write_bytes(b"%PDF verified")
            source = {"identifier": "doi:10.1234/verified", "doi": "10.1234/verified", "title": "Verified", "source_id": "verified", "local_path": str(pdf), "digest": research._digest(pdf), "evidence_fields": {"key_result": "4 confirmed molecules"}, "locators": ["paper.pdf#page=2"]}
            stage._write_manifest_file({"brief_revision": 1, "sources": [source], "evidence_matrix": {"evidence_levels": {}}})
            promoted = stage.promote_evidence("doi:10.1234/verified", locators=("paper.pdf#page=2",), verifier="human-editor")
            self.assertEqual(promoted["evidence_fields"]["evidence_level"], "VERIFIED")
            self.assertIn("VERIFIED_SOURCE_FACT", (project / "research" / "evidence-notes.md").read_text(encoding="utf-8"))

    def test_intent_optional_expert_review_isolated_and_confirmation_gated(self):
        intent = load_module("v2_intent_expert_review", V2_SKILLS["chemical-review-intent"] / "intent.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            stage = intent.IntentStage(project)
            stage.initialize("molecular discovery")
            stage.confirm({
                "research_question": "How are generated molecules experimentally validated?",
                "core_claims": ["Validation quality varies."], "scope": "Small molecules since 2020.",
                "exclusions": "No proteins.", "audience": "Chemists.", "contribution": "Evidence map.",
                "evidence_standards": "Original full text.", "boundary_scenarios": "Keep UNKNOWN.",
            })
            canonical_before = (project / "review-brief.md").read_bytes()
            (project / "stale.md").write_text("stale secret", encoding="utf-8")
            skipped = stage.optional_expert_review("skip", reviewer=lambda _payload: None)
            self.assertEqual(skipped.decision, "SKIPPED")
            self.assertEqual(canonical_before, (project / "review-brief.md").read_bytes())
            self.assertFalse((project / "review-brief.proposed.md").exists())

            class Reviewer:
                def __init__(self): self.payload = None
                def review(self, payload):
                    self.payload = payload
                    return {"findings": [{"id": "f1", "module": "evidence", "severity": "HIGH", "affected_field": "evidence_standards", "rationale": "Need identity confirmation.", "suggested_change": "Require identity confirmation and assay endpoint.", "confidence": "HIGH", "unresolved_questions": ["Which assay?"]}]}
            reviewer = Reviewer()
            report = stage.optional_expert_review("yes", reviewer=reviewer, materials=(project / "stale.md",))
            self.assertTrue(report.success)
            self.assertIn("evidence", stage.grouped_expert_findings())
            self.assertIn("advisory", (project / "expert-review-report.md").read_text(encoding="utf-8").lower())
            self.assertNotIn("stale secret", json.dumps(reviewer.payload))
            decision = stage.apply_expert_review_decision("accept-selected", selected=["f1"])
            self.assertEqual(decision, "PROPOSED")
            self.assertEqual(canonical_before, (project / "review-brief.md").read_bytes())
            self.assertTrue((project / "review-brief.proposed.md").exists())
            with self.assertRaises(intent.ConfirmationRequired):
                stage.read_confirmed()
            stage.confirm_change()
            self.assertIn("identity confirmation", (project / "review-brief.md").read_text(encoding="utf-8"))

    def test_intent_expert_failure_rejects_mutation_and_records_honest_boundary(self):
        intent = load_module("v2_intent_expert_failure", V2_SKILLS["chemical-review-intent"] / "intent.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            stage = intent.IntentStage(project)
            stage.initialize("chemistry")
            stage.confirm({key: ("claim",) if key == "core_claims" else "value" for key, _ in intent.FIELDS})
            before = (project / "review-brief.md").read_bytes()
            result = stage.optional_expert_review("yes", reviewer=lambda _payload: {"bad": "shape"})
            self.assertFalse(result.success)
            self.assertEqual(before, (project / "review-brief.md").read_bytes())
            self.assertIn("MALFORMED", (project / "expert-review-report.md").read_text(encoding="utf-8"))

    def test_intent_expert_timeout_returns_without_waiting_for_callback(self):
        intent = load_module("v2_intent_expert_timeout", V2_SKILLS["chemical-review-intent"] / "intent.py")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            stage = intent.IntentStage(project)
            stage.initialize("chemistry")
            stage.confirm({key: ("claim",) if key == "core_claims" else "value" for key, _ in intent.FIELDS})

            def slow_reviewer(_payload):
                time.sleep(0.25)
                return {"findings": []}

            started = time.monotonic()
            result = stage.optional_expert_review("yes", reviewer=slow_reviewer, timeout_seconds=0.01)
            elapsed = time.monotonic() - started
            self.assertFalse(result.success)
            self.assertIn("TIMEOUT", result.reason)
            self.assertLess(elapsed, 0.15)
            self.assertIn("TIMEOUT", (project / "expert-review-report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
