from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "chemical-review"
sys.path.insert(0, str(SKILL_DIR))

from orchestrator import ChemicalReviewOrchestrator  # noqa: E402
from delivery import DocxExportError, JournalProfile  # noqa: E402
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

    def test_confirmed_journal_requires_its_persisted_profile_for_docx_export(self):
        with TemporaryDirectory() as project_dir:
            root = Path(project_dir)
            orchestrator = self._confirmed_journal_project(root)
            root.joinpath("journal-profile.md").unlink()
            self._write_canonical_content(root)

            with self.assertRaisesRegex(DocxExportError, "confirmed target journal.*profile"):
                orchestrator.export_docx()

            state = ChemicalReviewOrchestrator(root).resume()
            self.assertEqual(state.status, "WAITING_FOR_HUMAN")
            self.assertEqual(state.human_action, "REQUIRED")
            self.assertIn("journal-profile.md", state.next_action)

    def test_docx_profile_must_match_the_confirmed_target_journal(self):
        with TemporaryDirectory() as project_dir:
            root = Path(project_dir)
            orchestrator = self._confirmed_journal_project(root)
            self._write_canonical_content(root)
            mismatched = JournalProfile.selected(
                target_journal="Other Chemistry",
                guide_locator="https://example.org/other/guide",
                guide_retrieved_at="2026-08-24",
                guide_digest="a" * 64,
                requirements=("margin: 1 inch",),
            )

            with self.assertRaisesRegex(DocxExportError, "does not match.*confirmed target journal"):
                orchestrator.export_docx(profile=mismatched)

            state = ChemicalReviewOrchestrator(root).resume()
            self.assertEqual(state.status, "WAITING_FOR_HUMAN")
            self.assertEqual(state.human_action, "REQUIRED")

    def test_in_memory_docx_profile_cannot_bypass_invalid_persisted_provenance(self):
        with TemporaryDirectory() as project_dir:
            root = Path(project_dir)
            orchestrator = self._confirmed_journal_project(root)
            self._write_canonical_content(root)
            profile_path = root / "journal-profile.md"
            profile_text = profile_path.read_text(encoding="utf-8")
            profile_path.write_text(
                profile_text.replace(
                    "https://example.org/example-chemistry/guide", "not-a-locator"
                )
                .replace("Retrieved at\n2026-08-23", "Retrieved at\n")
                .replace("Guide digest\n", "Guide digest\n" + "0" * 64 + "\n"),
                encoding="utf-8",
            )
            in_memory = JournalProfile.selected(
                target_journal="Example Chemistry",
                guide_locator="https://example.org/example-chemistry/guide",
                guide_retrieved_at="2026-08-23",
                guide_digest=hashlib.sha256(
                    b"Current official review guide."
                ).hexdigest(),
                requirements=("Margins: 1 inch",),
            )

            with self.assertRaisesRegex(DocxExportError, "journal profile|guide|locator"):
                orchestrator.export_docx(profile=in_memory)

            state = ChemicalReviewOrchestrator(root).resume()
            self.assertEqual(state.status, "WAITING_FOR_HUMAN")
            self.assertEqual(state.human_action, "REQUIRED")

    def test_docx_export_requires_confirmed_journal_state_when_intent_has_target(self):
        with TemporaryDirectory() as project_dir:
            root = Path(project_dir)
            orchestrator = self._confirmed_journal_project(root)
            self._write_canonical_content(root)
            self._persist_mapped_profile(root)
            state_path = root / "workflow-state.md"
            state_path.write_text(
                state_path.read_text(encoding="utf-8").replace(
                    "journal_confirmation: CONFIRMED",
                    "journal_confirmation: REQUIRED",
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(DocxExportError, "journal.*confirm"):
                orchestrator.export_docx()

            state = ChemicalReviewOrchestrator(root).resume()
            self.assertEqual(state.status, "WAITING_FOR_HUMAN")
            self.assertEqual(state.human_action, "REQUIRED")

    def test_docx_export_requires_intent_target_when_journal_state_is_confirmed(self):
        with TemporaryDirectory() as project_dir:
            root = Path(project_dir)
            orchestrator = self._confirmed_journal_project(root)
            self._write_canonical_content(root)
            self._persist_mapped_profile(root)
            intent_path = root / "review-intent.md"
            intent_path.write_text(
                intent_path.read_text(encoding="utf-8")
                .replace("target_journal: Example Chemistry\n", "")
                .replace("Target journal: Example Chemistry\n", ""),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(DocxExportError, "journal.*intent|target journal"):
                orchestrator.export_docx()

            state = ChemicalReviewOrchestrator(root).resume()
            self.assertEqual(state.status, "WAITING_FOR_HUMAN")
            self.assertEqual(state.human_action, "REQUIRED")

    @staticmethod
    def _persist_mapped_profile(root):
        JournalProfile.selected(
            target_journal="Example Chemistry",
            guide_locator="https://example.org/example-chemistry/guide",
            guide_retrieved_at="2026-08-23",
            guide_digest=hashlib.sha256(b"Current official review guide.").hexdigest(),
            requirements=("Margins: 1 inch",),
        ).persist(root)

    def _confirmed_journal_project(self, root):
        orchestrator = ChemicalReviewOrchestrator(root)
        orchestrator.start("condition-dependent nickel coupling")
        orchestrator.continue_grill(
            {
                "core_claim": "Mechanistic branches depend on reaction context.",
                "scope": "Nickel-mediated C-C coupling",
                "exclusions": "Palladium-only systems",
                "expected_contribution": "Reconcile apparently conflicting mechanisms.",
            }
        )
        candidate = JournalCandidate(
            target_journal="Example Chemistry",
            rationale="Fit",
            official_guide_locator="https://example.org/example-chemistry/guide",
        )
        orchestrator.propose_journal_candidates((candidate,))
        orchestrator.confirm_journal_candidate(candidate.target_journal)
        orchestrator.fetch_selected_journal_guide(fetcher=_SnapshotFetcher())
        orchestrator.confirm_current_intent()
        return orchestrator

    @staticmethod
    def _write_canonical_content(root):
        root.joinpath("review-content.md").write_text(
            "---\n"
            "kind: single-review-content-source\n"
            "schema: 1\n"
            "content_revision: 1\n"
            "---\n\n"
            "# Review Content Source\n\n"
            "## Content blocks\n\n"
            "### Merge 1 · Block 1\n"
            "Section: Background\n"
            "Claim level: MODEL_SYNTHESIS\n"
            "Contribution type: explanation\n"
            "Source units: unit-1\n"
            "Evidence IDs: paper-1\n"
            "Comparability status: NOT_APPLICABLE\n"
            "Comparability basis: Not recorded.\n"
            "Text:\nA bounded synthesis.\n",
            encoding="utf-8",
        )


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
