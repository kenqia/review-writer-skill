from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "chemical-review"
sys.path.insert(0, str(SKILL_DIR))

from orchestrator import ChemicalReviewOrchestrator  # noqa: E402
from research import OpenAlexDiscoveryAdapter, ResearchConfig  # noqa: E402
from review import (  # noqa: E402
    HttpJournalGuideFetcher,
    JournalCandidate,
    JournalGuideSnapshot,
)


class JournalAndOpenAlexTests(unittest.TestCase):
    def test_missing_journal_offers_confirmable_candidates_before_research(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("condition-dependent nickel coupling")

            result = orchestrator.continue_grill(
                {
                    "core_claim": "Mechanistic branches depend on ligand and substrate context.",
                    "scope": "Nickel-mediated C-C coupling",
                    "exclusions": "Palladium-only systems",
                    "expected_contribution": "Reconcile apparently conflicting mechanisms.",
                }
            )

            self.assertEqual(result.status, "WAITING_FOR_HUMAN")
            self.assertIn("journal candidates", result.next_action.lower())

            candidates = (
                JournalCandidate(
                    target_journal="Example Chemistry",
                    rationale="Best fit for a critical mechanistic narrative review.",
                    official_guide_locator="https://example.org/example-chemistry/guide",
                ),
                JournalCandidate(
                    target_journal="Chemical Perspectives",
                    rationale="Broader audience and longer review format.",
                    official_guide_locator="https://example.org/chemical-perspectives/guide",
                ),
            )
            proposed = orchestrator.propose_journal_candidates(candidates)
            self.assertEqual(proposed.intent_confirmation, "REQUIRED")

            confirmed = orchestrator.confirm_journal_candidate("Example Chemistry")
            self.assertEqual(confirmed.assets["journal_status"], "SELECTED")
            intent = Path(project_dir, "review-intent.md").read_text(encoding="utf-8")
            self.assertIn("Target journal: Example Chemistry", intent)
            self.assertIn("example-chemistry/guide", intent)

            fetched = orchestrator.fetch_selected_journal_guide(
                fetcher=_SnapshotFetcher()
            )
            self.assertEqual(fetched.assets["journal_guide_status"], "FETCHED")
            self.assertEqual(orchestrator.confirm_current_intent().phase, "RESEARCH")

    def test_http_journal_guide_fetcher_records_official_snapshot(self):
        payload = b"<html><title>Example Chemistry author guide</title><p>Review format.</p></html>"

        def fake_open(request, timeout):
            self.assertEqual(request.full_url, "https://example.org/guide")
            self.assertEqual(timeout, 7.5)
            return _FakeResponse(payload)

        snapshot = HttpJournalGuideFetcher(timeout=7.5, opener=fake_open).fetch(
            JournalCandidate(
                target_journal="Example Chemistry",
                rationale="Fit",
                official_guide_locator="https://example.org/guide",
            )
        )

        self.assertEqual(snapshot.target_journal, "Example Chemistry")
        self.assertIn("author guide", snapshot.content)
        self.assertTrue(snapshot.content_digest)
        self.assertEqual(snapshot.source_locator, "https://example.org/guide")

    def test_openalex_adapter_parses_real_work_response_shape(self):
        payload = {
            "results": [
                {
                    "id": "https://openalex.org/W1",
                    "title": "Condition-dependent nickel coupling",
                    "authorships": [
                        {"author": {"display_name": "A. Researcher"}},
                        {"author": {"display_name": "B. Chemist"}},
                    ],
                    "publication_year": 2024,
                    "doi": "https://doi.org/10.1234/example",
                    "primary_location": {
                        "landing_page_url": "https://doi.org/10.1234/example"
                    },
                    "keywords": [{"display_name": "nickel coupling"}],
                    "referenced_works": ["https://openalex.org/W2"],
                    "abstract_inverted_index": {"Nickel": [0], "coupling": [1]},
                }
            ]
        }
        requests = []

        def fake_fetch(request, timeout):
            requests.append((request.full_url, timeout))
            return json.dumps(payload).encode("utf-8")

        adapter = OpenAlexDiscoveryAdapter(
            requester=fake_fetch,
            per_page=3,
            timeout=4.0,
        )
        papers = adapter.search("nickel coupling", "methods/materials")

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].identifier, "https://openalex.org/W1")
        self.assertEqual(papers[0].title, "Condition-dependent nickel coupling")
        self.assertEqual(papers[0].authors, ("A. Researcher", "B. Chemist"))
        self.assertEqual(papers[0].abstract, "Nickel coupling")
        self.assertEqual(papers[0].cited_identifiers, ("https://openalex.org/W2",))
        self.assertEqual(len(requests), 1)
        self.assertIn("search=nickel+coupling", requests[0][0])
        self.assertIn("per-page=3", requests[0][0])

    def test_default_research_config_has_a_real_openalex_route(self):
        config = ResearchConfig.default()
        self.assertEqual([adapter.name for adapter in config.discovery], ["OpenAlex"])


class _FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.payload


class _SnapshotFetcher:
    def fetch(self, candidate):
        return JournalGuideSnapshot(
            target_journal=candidate.target_journal,
            source_locator=candidate.official_guide_locator,
            content="Current official review guide.",
            retrieved_at="2026-08-23",
        )


if __name__ == "__main__":
    unittest.main()
