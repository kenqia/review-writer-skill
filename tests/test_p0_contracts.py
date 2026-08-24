from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "chemical-review"
sys.path.insert(0, str(SKILL_DIR))

from orchestrator import ChemicalReviewOrchestrator, _document  # noqa: E402
import research  # noqa: E402
from research import (  # noqa: E402
    FullTextResult,
    ParsedDocument,
    PaperRecord,
    ResearchConfig,
)
from units import (  # noqa: E402
    ClaimBlock,
    ResearchWritingUnit,
    UnitManager,
    UnitResult,
)


class _Discovery:
    name = "OpenAlex"

    def __init__(self, papers):
        self.papers = tuple(papers)

    def search(self, query, path):
        return self.papers


class _FullText:
    name = "Unpaywall"

    def fetch(self, paper):
        return FullTextResult(
            paper.identifier,
            "FOUND",
            "authorized full text",
            self.name,
            locator="paper.pdf#Results",
            access_basis="OPEN_ACCESS",
        )


class _Parser:
    name = "MinerU"

    def parse(self, full_text):
        return ParsedDocument(
            full_text.paper_id,
            self.name,
            sections=("Results",),
            locators=("paper.pdf#Results",),
        )


class P0ContractTests(unittest.TestCase):
    def test_metadata_only_is_discovery_ready_and_doi_identity_is_stable(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._research_project(project_dir)
            doi_url = "https://doi.org/10.1234/Example"
            result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(_Discovery((PaperRecord(doi_url, "Metadata-only paper"),)),)
                )
            )

            self.assertEqual(result.assets["readiness"], "DISCOVERY_READY")
            self.assertEqual(orchestrator.resume().assets["readiness"], "DISCOVERY_READY")
            literature = Path(project_dir, "literature-set.md").read_text(encoding="utf-8")
            self.assertIn(doi_url, literature)
            self.assertEqual(
                research.canonical_evidence_id(doi_url),
                research.canonical_evidence_id("doi:10.1234/example"),
            )

    def test_source_fact_from_metadata_only_cannot_enter_central_merge(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                evidence_id="https://doi.org/10.1234/example",
                readiness="DISCOVERY_READY",
                units=(self._unit("source-fact"),),
            )
            with self.assertRaisesRegex(ValueError, "SOURCE_FACT.*EVIDENCE_READY"):
                orchestrator.submit_review_unit_result(
                    self._result(
                        "source-fact",
                        claim_level="SOURCE_FACT",
                        evidence_ids=("doi:10.1234/example",),
                    )
                )

    def test_valid_https_doi_claim_is_written_and_projected_as_claim_ready(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                evidence_id="https://doi.org/10.1234/example",
                readiness="EVIDENCE_READY",
                units=(self._unit("source-fact"),),
            )
            submitted = orchestrator.submit_review_unit_result(
                self._result(
                    "source-fact",
                    claim_level="SOURCE_FACT",
                    evidence_ids=("doi:10.1234/example",),
                )
            )
            self.assertEqual(submitted.status, "READY_FOR_NEXT_PHASE")
            merged = orchestrator.merge_review_units(("source-fact",))

            self.assertEqual(merged.status, "READY_FOR_NEXT_PHASE")
            self.assertEqual(merged.assets["readiness"], "CLAIM_READY")
            self.assertIn("Source-backed claim", Path(project_dir, "review-content.md").read_text(encoding="utf-8"))
            self.assertIn("content_digest", merged.assets)
            self.assertEqual(
                Path(project_dir, "units", "source-fact.md")
                .read_text(encoding="utf-8")
                .split("status: ", 1)[1]
                .splitlines()[0],
                "MERGED",
            )

    def test_cross_study_claim_requires_explicit_chemistry_comparability(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                units=(self._unit("cross-study"),),
            )
            literature = Path(project_dir, "literature-set.md")
            literature.write_text(
                literature.read_text(encoding="utf-8")
                + "\n## Extension\n- paper-2: Second evidence [readiness: EVIDENCE_READY]\n",
                encoding="utf-8",
            )
            orchestrator.submit_review_unit_result(
                self._result(
                    "cross-study",
                    claim_level="MODEL_SYNTHESIS",
                    evidence_ids=("paper-1", "paper-2"),
                )
            )

            merged = orchestrator.merge_review_units(("cross-study",))
            self.assertEqual(merged.assets["readiness"], "EVIDENCE_READY")

    def test_later_single_source_merge_cannot_hide_an_existing_comparability_gap(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                units=(self._unit("cross-study"), self._unit("single-source")),
            )
            literature = Path(project_dir, "literature-set.md")
            literature.write_text(
                literature.read_text(encoding="utf-8")
                + "\n## Extension\n- paper-2: Second evidence [readiness: EVIDENCE_READY]\n",
                encoding="utf-8",
            )
            orchestrator.submit_review_unit_result(
                self._result(
                    "cross-study",
                    claim_level="MODEL_SYNTHESIS",
                    evidence_ids=("paper-1", "paper-2"),
                )
            )
            orchestrator.submit_review_unit_result(self._result("single-source"))

            first = orchestrator.merge_review_units(("cross-study",))
            self.assertEqual(first.assets["readiness"], "EVIDENCE_READY")
            final = orchestrator.merge_review_units(("single-source",))

            self.assertEqual(final.assets["readiness"], "EVIDENCE_READY")
            content = Path(project_dir, "review-content.md").read_text(encoding="utf-8")
            self.assertIn("readiness: EVIDENCE_READY", content)

    def test_execution_mode_persists_and_continuous_batch_merges_once(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(
                project_dir,
                mode="continuous",
                units=(self._unit("first"), self._unit("second")),
            )
            first = self._result("first", evidence_ids=("paper-1",))
            second = self._result("second", evidence_ids=("paper-1",))
            result = orchestrator.submit_ready_unit_results((first, second))

            self.assertEqual(result.assets["execution_mode"], "continuous")
            self.assertEqual(result.assets["readiness"], "CLAIM_READY")
            content_path = Path(project_dir, "review-content.md")
            content = content_path.read_text(encoding="utf-8")
            self.assertEqual(content.count("Source-backed claim"), 2)
            resumed = ChemicalReviewOrchestrator(project_dir).resume()
            self.assertEqual(resumed.execution_mode, "continuous")
            repeated = ChemicalReviewOrchestrator(project_dir).submit_ready_unit_results(
                (first, second)
            )
            self.assertEqual(repeated.assets["execution_mode"], "continuous")
            self.assertEqual(content_path.read_text(encoding="utf-8").count("Source-backed claim"), 2)

    def test_acceptance_mode_pauses_at_unit_boundary_and_hard_blocker_is_actionable(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._implementation_project(project_dir, mode="acceptance")
            blocked = self._result(
                "first",
                human_action_required="Provide an authorized PDF for this source.",
            )
            result = orchestrator.submit_ready_unit_results((blocked,))

            self.assertEqual(result.execution_mode, "acceptance")
            self.assertEqual(result.status, "WAITING_FOR_HUMAN")
            self.assertEqual(result.human_action, "REQUIRED")
            self.assertIn("HUMAN_ACTION_REQUIRED", result.next_action)
            self.assertIn("authorized PDF", result.next_action)
            self.assertEqual(ChemicalReviewOrchestrator(project_dir).resume().execution_mode, "acceptance")

    def _research_project(self, project_dir):
        orchestrator = ChemicalReviewOrchestrator(project_dir)
        orchestrator.start("nickel catalysis")
        orchestrator.continue_grill(
            {
                "core_claims": "Mechanism depends on condition.",
                "scope": "Nickel catalysis",
                "exclusions": "Palladium-only systems",
                "audience": "Chemistry researchers",
                "contribution": "Compare mechanism boundaries.",
            }
        )
        orchestrator.confirm_current_intent()
        return orchestrator

    def _implementation_project(
        self,
        project_dir,
        *,
        mode="acceptance",
        evidence_id="paper-1",
        readiness="EVIDENCE_READY",
        units=None,
    ):
        root = Path(project_dir)
        root.joinpath("review-intent.md").write_text(
            _document({"kind": "review-intent", "schema": "1"}, "# Review Intent\n"),
            encoding="utf-8",
        )
        root.joinpath("domain-profile.md").write_text(
            _document({"kind": "domain-profile", "schema": "1"}, "# Domain Profile\n"),
            encoding="utf-8",
        )
        root.joinpath("review-blueprint.md").write_text(
            _document({"kind": "review-blueprint", "schema": "1"}, "# Review Blueprint\n"),
            encoding="utf-8",
        )
        root.joinpath("research-evidence.md").write_text(
            _document({"kind": "research-evidence", "schema": "1"}, "# Research Evidence\n"),
            encoding="utf-8",
        )
        root.joinpath("literature-set.md").write_text(
            _document(
                {"kind": "layered-literature-set", "schema": "1"},
                "# Layered Literature Set\n\n"
                "## Anchor/core\n"
                f"- {evidence_id}: Evidence [readiness: {readiness}]\n",
            ),
            encoding="utf-8",
        )
        root.joinpath("workflow-state.md").write_text(
            _document(
                {
                    "kind": "chemical-review-workflow-state",
                    "schema": "1",
                    "phase": "ISSUES",
                    "status": "READY_FOR_NEXT_PHASE",
                    "next_action": "Accept unit plan.",
                    "execution_mode": mode,
                    "human_action": "NONE",
                },
                "# Workflow State\n\n## Open questions and risks\nNone.\n\n## Resume note\nReady.\n",
            ),
            encoding="utf-8",
        )
        orchestrator = ChemicalReviewOrchestrator(project_dir)
        selected_units = tuple(units or (self._unit("first"),))
        UnitManager(project_dir).create_plan(selected_units)
        orchestrator.accept_unit_plan()
        return orchestrator

    def _unit(self, unit_id):
        return ResearchWritingUnit(
            unit_id=unit_id,
            kind="section_claim",
            purpose=f"Resolve {unit_id}.",
            prerequisites=(),
            completion_signal=f"A result for {unit_id} is recorded.",
            remaining_uncertainty="Broader evidence may revise this result.",
        )

    def _result(
        self,
        unit_id,
        *,
        claim_level="MODEL_SYNTHESIS",
        evidence_ids=("paper-1",),
        human_action_required="",
    ):
        return UnitResult(
            unit_id=unit_id,
            completion_evidence=f"Completed {unit_id}.",
            findings=(f"Finding from {unit_id}.",),
            claims=(
                ClaimBlock(
                    section="Evidence boundary",
                    claim_level=claim_level,
                    contribution_type="explanation",
                    text="Source-backed claim",
                    evidence_ids=evidence_ids,
                ),
            ),
            remaining_uncertainty="Broader evidence may revise this result.",
            human_action_required=human_action_required,
        )


if __name__ == "__main__":
    unittest.main()
