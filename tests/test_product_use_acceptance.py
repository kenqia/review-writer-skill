from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "chemical-review"
sys.path.insert(0, str(SKILL_DIR))

from delivery import FigureAsset, FigureInventory  # noqa: E402
from orchestrator import ChemicalReviewOrchestrator  # noqa: E402
from prototype import BlueprintProposal, PrototypeSignal, PrototypeSubmission  # noqa: E402
from research import (  # noqa: E402
    FullTextResult,
    ParsedDocument,
    PaperRecord,
    ResearchBudget,
    ResearchConfig,
)
from review import ReviewAssessment  # noqa: E402
from units import ClaimBlock, ResearchWritingUnit, UnitResult  # noqa: E402


class _Discovery:
    name = "OpenAlex"

    def search(self, query, path):
        return (
            PaperRecord(
                "paper-1",
                "Ligand-controlled nickel coupling",
                source=self.name,
                layer="anchor/core",
                keywords=("nickel", "ligand"),
            ),
            PaperRecord(
                "paper-2",
                "Competing radical pathways",
                source=self.name,
                layer="controversy",
                keywords=("nickel", "radical"),
            ),
        )


class _FullText:
    name = "Unpaywall"

    def fetch(self, paper):
        return FullTextResult(
            paper.identifier,
            "FOUND",
            f"Authorized text for {paper.identifier}",
            self.name,
            locator=f"{paper.identifier}.pdf#Results",
            access_basis="OPEN_ACCESS",
        )


class _Parser:
    name = "MinerU"

    def parse(self, full_text):
        return ParsedDocument(
            full_text.paper_id,
            self.name,
            sections=("Results",),
            locators=(full_text.locator,),
        )


class ProductUseAcceptanceTests(unittest.TestCase):
    """Fresh, user-visible slices for ticket #19 (not scientific acceptance)."""

    def _grill(self, root, topic):
        orchestrator = ChemicalReviewOrchestrator(root)
        first = orchestrator.start(topic, mode="continuous")
        self.assertEqual(first.execution_mode, "continuous")
        grilled = orchestrator.continue_grill(
            {
                "core_claims": "Mechanistic branches depend on reaction context.",
                "scope": "Nickel-mediated C-C coupling",
                "exclusions": "Palladium-only systems",
                "audience": "Chemistry researchers",
                "contribution": "Reconcile condition-dependent evidence",
            }
        )
        self.assertEqual(grilled.status, "READY_FOR_NEXT_PHASE")
        confirmed = orchestrator.confirm_current_intent()
        self.assertEqual(confirmed.phase, "RESEARCH")
        self.assertEqual(confirmed.execution_mode, "continuous")
        return orchestrator

    def test_topic_only_has_honest_degraded_handoff_without_pause_loop(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = self._grill(Path(project_dir), "topic-only nickel mechanism review")
            result = orchestrator.run_research(ResearchConfig.no_key_fallback())

            self.assertEqual(result.status, "READY_FOR_NEXT_PHASE")
            self.assertEqual(result.assets["readiness"], "DISCOVERY_READY")
            self.assertEqual(result.assets["research_handoff"], "PROTOTYPE")
            self.assertIn("NO_KEY_FALLBACK", Path(project_dir, "research-evidence.md").read_text())
            self.assertTrue(Path(project_dir, "coverage-matrix.md").is_file())
            self.assertTrue(Path(project_dir, "run-budget.json").is_file())
            self.assertTrue(Path(project_dir, "research-setup-wizard.md").is_file())
            self.assertIn("metadata", result.next_action.lower())
            self.assertNotEqual(result.assets["readiness"], "EVIDENCE_READY")

    def test_authorized_pdf_path_reaches_candidate_with_source_bound_delivery_evidence(self):
        with TemporaryDirectory() as project_dir:
            root = Path(project_dir)
            authorized_pdf = root / "authorized-papers" / "paper.pdf"
            authorized_pdf.parent.mkdir()
            authorized_pdf.write_bytes(b"%PDF-1.7 authorized fixture")
            nested_pdf = authorized_pdf.parent / "nested" / "ignored.pdf"
            nested_pdf.parent.mkdir()
            nested_pdf.write_bytes(b"%PDF-1.7 nested fixture")
            orchestrator = self._grill(root, "authorized PDF nickel mechanism review")
            research_result = orchestrator.run_research(
                ResearchConfig(
                    discovery=(_Discovery(),),
                    full_text=(_FullText(),),
                    parsers=(_Parser(),),
                    authorized_pdf_dir=authorized_pdf.parent,
                    budget=ResearchBudget(max_queries=10, max_requests=30),
                )
            )

            self.assertEqual(research_result.assets["readiness"], "EVIDENCE_READY")
            literature = (root / "literature-set.md").read_text(encoding="utf-8")
            self.assertIn("readiness: EVIDENCE_READY", literature)
            registry = (root / "source-registry.md").read_text(encoding="utf-8")
            self.assertIn("USER_PDF", registry)
            self.assertIn("USER_AUTHORIZED", registry)
            self.assertIn("PARSED", registry)
            self.assertIn("paper-1.pdf#Results", registry)
            self.assertNotIn("ignored.pdf", registry)
            resumed_research = ChemicalReviewOrchestrator(root).resume()
            self.assertEqual(
                Path(resumed_research.assets["authorized_pdf_dir"]),
                authorized_pdf.parent,
            )
            self.assertIn(
                str(authorized_pdf),
                resumed_research.assets["authorized_pdf_paths"],
            )

            orchestrator.accept_research_handoff()
            orchestrator.run_prototype(
                PrototypeSubmission(
                    paper_ids=("paper-1", "paper-2"),
                    representative_reason="Anchor and controversy papers expose the boundary.",
                    value_argument="A condition-centred comparison changes the interpretation beyond summary.",
                    signals=(
                        PrototypeSignal(
                            kind="comparison",
                            statement="Compare ligand and radical branches under reported conditions.",
                            evidence_ids=("paper-1", "paper-2"),
                            value_gain="Makes the disagreement testable rather than merely juxtaposed.",
                        ),
                        PrototypeSignal(
                            kind="explanation",
                            statement="Different resting states may explain the reported branches.",
                            evidence_ids=("paper-1", "paper-2"),
                            value_gain="Provides a bounded synthesis for downstream writing.",
                        ),
                    ),
                )
            )
            orchestrator.accept_prototype_handoff()
            orchestrator.build_review_blueprint(
                BlueprintProposal(
                    section_structure=("Background", "Mechanistic comparison"),
                    narrative_line="Move from reports to condition-dependent branches.",
                    comparison_dimensions=("ligand", "substrate", "mechanistic probe"),
                    evidence_strategy=("source PDF", "locator-bound parse", "comparability check"),
                    target_journal_requirements=("Generic chemistry formatting until a journal is selected.",),
                    known_risks=("Operando speciation remains incomplete.",),
                    candidate_units=("Draft mechanism claim",),
                )
            )
            orchestrator.accept_review_blueprint()
            orchestrator.create_review_units(
                (
                    ResearchWritingUnit(
                        unit_id="mechanism-claim",
                        kind="section_claim",
                        purpose="Draft a locator-bound mechanism comparison.",
                        prerequisites=(),
                        completion_signal="A source-bound claim and uncertainty are recorded.",
                        remaining_uncertainty="Operando speciation remains incomplete.",
                    ),
                )
            )
            orchestrator.accept_unit_plan()
            merged = orchestrator.submit_ready_unit_results(
                (
                    UnitResult(
                        unit_id="mechanism-claim",
                        completion_evidence="Compared both parsed source records.",
                        findings=("The reports diverge under different ligand contexts.",),
                        claims=(
                            ClaimBlock(
                                section="Mechanistic comparison",
                                claim_level="SOURCE_FACT",
                                contribution_type="comparison",
                                text="The selected studies report different favored pathways.",
                                evidence_ids=("paper-1", "paper-2"),
                                comparability_status="COMPARABLE",
                                comparability_basis=(
                                    "Compared the reported reaction context, endpoint, and mechanistic probe; "
                                    "unreported conditions remain explicit uncertainty."
                                ),
                            ),
                        ),
                        remaining_uncertainty="Operando speciation remains incomplete.",
                    ),
                )
            )
            self.assertEqual(merged.assets["readiness"], "CLAIM_READY")
            self.assertTrue((root / "review-content.md").is_file())
            content = (root / "review-content.md").read_text(encoding="utf-8")
            claim_id = re.search(r"^### (Merge .+)$", content, flags=re.MULTILINE).group(1)

            image_path = root / "paper-1-figure.png"
            Image.new("RGB", (120, 80), "white").save(image_path)
            inventory = FigureInventory(root)
            inventory.register_source_figure(
                FigureAsset(
                    asset_id="fig-1",
                    source_id="paper-1",
                    source_path=image_path.name,
                    locator="paper-1.pdf#Figure 2, p. 4",
                    caption="Source mechanism figure.",
                    provenance="Cropped from the authorized source paper.",
                    target_section="Mechanistic comparison",
                    target_paragraph="P-1",
                    claim_ids=(claim_id,),
                    citation_ids=("paper-1",),
                    extraction_status="VERIFIED",
                )
            )
            inventory.persist()
            exported = orchestrator.export_docx()
            self.assertTrue(exported.output_path.is_file())
            manifest = exported.manifest_path.read_text(encoding="utf-8")
            self.assertIn("figure_count: 1", manifest)
            self.assertIn("source_digest:", manifest)

            reviewed = orchestrator.run_review(
                ReviewAssessment(
                    value_status="VALUE_PRODUCING",
                    value_notes=("The condition-centred comparison adds a testable synthesis.",),
                    chemical_reasoning_notes=("The claim stays bounded by the two parsed source locators.",),
                    intent_alignment_notes=("The draft answers the confirmed nickel mechanism question.",),
                    revision_requests=(),
                    nonblocking_uncertainties=("Operando speciation remains incomplete.",),
                    integrity_findings=(),
                ),
                None,
            )
            self.assertEqual(reviewed.status, "CANDIDATE_READY")
            package = (root / "submission-candidate-package.md").read_text(encoding="utf-8")
            for asset in (
                "source-registry.md",
                "coverage-matrix.md",
                "figure-inventory.md",
                "generic-chemistry-draft.docx.manifest.md",
            ):
                self.assertIn(asset, package)

            ledger = json.loads((root / "run-budget.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(ledger["query_count"], 1)
            self.assertGreaterEqual(ledger["parser_pages"], 1)
            self.assertGreaterEqual(ledger["parser_chunks"], 1)
            self.assertIn("EVIDENCE_READY", literature)
            self.assertIn("CLAIM_READY", merged.assets["readiness"])


if __name__ == "__main__":
    unittest.main()
