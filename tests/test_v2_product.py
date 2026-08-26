from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from scripts.plugin_boundary import V2_SKILL_FILES


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / ".agents" / "skills"
PLUGIN = ROOT / "plugins" / "chemical-review" / "skills"
FIXTURE = ROOT / "tests" / "fixtures" / "v2-fresh-project"


SKILL_BUNDLES = {
    skill: tuple(sorted(path for path in files if path.endswith(".md") and path != "SKILL.md"))
    for skill, files in V2_SKILL_FILES.items()
}


class LightweightChemicalReviewTests(unittest.TestCase):
    def test_canonical_and_plugin_contain_only_markdown_skill_bundles(self):
        for skill_name, references in SKILL_BUNDLES.items():
            for root in (CANONICAL / skill_name, PLUGIN / skill_name):
                self.assertTrue((root / "SKILL.md").is_file(), root)
                self.assertTrue((root / "agents" / "openai.yaml").is_file(), root)
                for reference in references:
                    self.assertTrue((root / reference).is_file(), root / reference)
                self.assertEqual(
                    {
                        path.suffix
                        for path in root.rglob("*")
                        if path.is_file() and "__pycache__" not in path.parts
                    },
                    {".md", ".yaml"},
                    root,
                )

    def test_no_stage_runner_or_state_machine_is_in_the_skill_surface(self):
        for root in (CANONICAL, PLUGIN):
            for path in root.glob("chemical-review-*"):
                self.assertFalse(list(path.rglob("*.py")), path)
                text = "\n".join(
                    file.read_text(encoding="utf-8")
                    for file in path.rglob("*")
                    if file.is_file() and file.suffix in {".md", ".yaml"}
                ).lower()
                self.assertNotIn("state machine", text, path)
                self.assertNotIn("runner", text, path)

    def test_intent_keeps_a_small_grill_with_docs_loop_and_optional_advisory(self):
        skill = CANONICAL / "chemical-review-intent"
        main = (skill / "SKILL.md").read_text(encoding="utf-8")
        grilling = (skill / "grilling.md").read_text(encoding="utf-8")
        self.assertIn("grilling.md", main)
        self.assertIn("domain-modeling.md", main)
        self.assertIn("brief-contract.md", main)
        self.assertIn("result-and-revision.md", main)
        self.assertIn("design tree", grilling)
        self.assertIn("推荐答案", grilling)
        self.assertIn("fresh sub-agent", main)
        self.assertIn("advisory", main)

    def test_intent_preserves_answer_provenance_and_explicit_confirmation(self):
        skill = CANONICAL / "chemical-review-intent"
        grilling = (skill / "grilling.md").read_text(encoding="utf-8")
        contract = (skill / "brief-contract.md").read_text(encoding="utf-8")
        result = (skill / "result-and-revision.md").read_text(encoding="utf-8")
        for marker in ("MODEL_QUESTION", "USER_ANSWER", "DEFAULT", "UNKNOWN"):
            self.assertIn(marker, grilling)
        for marker in (
            "research question",
            "core-claim candidates",
            "scope",
            "exclusions",
            "audience",
            "contribution",
            "evidence expectations",
            "explicit confirmation",
            "review-brief.proposed.md",
        ):
            self.assertIn(marker, contract)
        for marker in (
            "stage result summary",
            "revision snapshot",
            "earliest affected stage",
            "do not silently overwrite",
            "WAITING_FOR_USER",
        ):
            self.assertIn(marker, result)

    def test_intent_advisory_is_opt_in_isolated_and_two_step(self):
        skill = CANONICAL / "chemical-review-intent"
        main = (skill / "SKILL.md").read_text(encoding="utf-8").lower()
        expert = (skill / "expert-review.md").read_text(encoding="utf-8").lower()
        contract = (skill / "brief-contract.md").read_text(encoding="utf-8").lower()
        result = (skill / "result-and-revision.md").read_text(encoding="utf-8").lower()

        for marker in (
            "explicitly asked",
            "only after",
            "confirmed brief",
            "fresh",
            "role prompt",
            "allowlist",
            "do not browse",
            "do not call providers",
            "hidden context",
            "do not edit",
        ):
            self.assertIn(marker, main + expert)
        for marker in (
            "grouped",
            "module",
            "severity",
            "rationale",
            "suggested change",
            "confidence",
            "unresolved questions",
            "skip",
            "accept selected",
            "reject all",
            "defer",
            "unconfirmed proposal",
            "second explicit confirmation",
        ):
            self.assertIn(marker, expert + contract)
        for marker in (
            "timeout",
            "unavailable",
            "malformed",
            "canonical brief unchanged",
            "report the reason",
        ):
            self.assertIn(marker, expert + contract + result)

    def test_research_documents_are_guidance_not_a_scripted_gate(self):
        skill = CANONICAL / "chemical-review-research"
        main = (skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("preflight.md", main)
        self.assertIn("discovery-and-screening.md", main)
        self.assertIn("candidate-acceptance.md", main)
        self.assertIn("full-text-and-resume.md", main)
        self.assertIn("evidence-and-handoff.md", main)
        self.assertIn("Markdown", main)
        preflight = (skill / "preflight.md").read_text(encoding="utf-8")
        discovery = (skill / "discovery-and-screening.md").read_text(encoding="utf-8")
        acceptance = (skill / "candidate-acceptance.md").read_text(encoding="utf-8")
        self.assertIn("configure_and_continue", preflight)
        self.assertIn("confirm_formal_start", preflight)
        for marker in ("pass", "failure", "not-verified", "official", "rerun"):
            self.assertIn(marker, preflight.lower())
        self.assertIn("accept_candidates", (skill / "discovery-and-screening.md").read_text(encoding="utf-8"))
        for marker in ("raw hits", "stable identity", "coverage", "MAYBE", "false-positive", "primary"):
            self.assertIn(marker.lower(), discovery.lower())
        for marker in ("high-impact checkpoint", "accept", "return", "full-text", "only accepted"):
            self.assertIn(marker.lower(), acceptance.lower())
        self.assertIn("SOURCE_EXCERPT", (skill / "evidence-and-handoff.md").read_text(encoding="utf-8"))
        self.assertNotIn("manifest.json", main)

    def test_research_evidence_keeps_legal_access_and_resume_boundaries(self):
        skill = CANONICAL / "chemical-review-research"
        full_text = (skill / "full-text-and-resume.md").read_text(encoding="utf-8")
        evidence = (skill / "evidence-and-handoff.md").read_text(encoding="utf-8")
        for marker in (
            "legal download request",
            "ambiguous",
            "stable identity",
            "authorized",
            "SOURCE_EXCERPT",
            "VERIFIED_SOURCE_FACT",
            "original PDF",
            "locator",
            "parser probe",
            "per-run",
            "resume",
        ):
            self.assertIn(marker.lower(), full_text.lower() + evidence.lower())
        for marker in ("UNKNOWN", "NOT_COMPARABLE", "Chemical GAP", "marginal", "uncovered", "budget", "retry"):
            self.assertIn(marker.lower(), evidence.lower())

    def test_synthesis_documents_keep_one_draft_without_code_or_payloads(self):
        skill = CANONICAL / "chemical-review-synthesis"
        main = (skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("planning.md", main)
        self.assertIn("drafting.md", main)
        self.assertIn("handoff.md", main)
        self.assertIn("draft.md", main)
        drafting = (skill / "drafting.md").read_text(encoding="utf-8")
        self.assertIn("SOURCE_FACT", drafting)
        self.assertIn("MODEL_SYNTHESIS", drafting)
        self.assertIn("MODEL_HYPOTHESIS", drafting)

    def test_synthesis_keeps_plan_checkpoint_partial_scope_and_single_authority(self):
        skill = CANONICAL / "chemical-review-synthesis"
        main = (skill / "SKILL.md").read_text(encoding="utf-8")
        planning = (skill / "planning.md").read_text(encoding="utf-8")
        drafting = (skill / "drafting.md").read_text(encoding="utf-8")
        handoff = (skill / "handoff.md").read_text(encoding="utf-8")
        for marker in ("allowlist", "confirmed brief", "Research", "draft.md", "reader-draft.md", "research-draft.md"):
            self.assertIn(marker.lower(), main.lower())
        for marker in ("comparison spine", "evidence distribution", "gaps", "confirm", "before formal drafting"):
            self.assertIn(marker.lower(), planning.lower())
        for marker in ("conditions", "comparator", "denominator", "limitation", "partial-scope", "UNKNOWN", "NOT_COMPARABLE", "Chemical GAP"):
            self.assertIn(marker.lower(), drafting.lower())
        for marker in ("high-risk", "counterexample", "next action", "QA", "separate", "confirmation"):
            self.assertIn(marker.lower(), handoff.lower())

    def test_qa_documents_describe_fresh_roles_and_human_feedback(self):
        skill = CANONICAL / "chemical-review-qa"
        main = (skill / "SKILL.md").read_text(encoding="utf-8")
        reviewers = (skill / "reviewers.md").read_text(encoding="utf-8")
        routing = (skill / "revision-routing.md").read_text(encoding="utf-8")
        self.assertIn("reviewers.md", main)
        self.assertIn("arbiter.md", main)
        self.assertIn("revision-routing.md", main)
        self.assertIn("fresh sub-agent", reviewers)
        self.assertIn("保留冲突", (skill / "arbiter.md").read_text(encoding="utf-8"))
        for disposition in ("accept", "reject", "defer"):
            self.assertIn(disposition, routing)
        self.assertIn("普通语言", routing)

    def test_qa_keeps_four_isolated_roles_incomplete_handling_and_traceable_findings(self):
        skill = CANONICAL / "chemical-review-qa"
        main = (skill / "SKILL.md").read_text(encoding="utf-8")
        reviewers = (skill / "reviewers.md").read_text(encoding="utf-8")
        arbiter = (skill / "arbiter.md").read_text(encoding="utf-8")
        routing = (skill / "revision-routing.md").read_text(encoding="utf-8")
        for marker in ("optional", "four", "fresh", "allowlist", "same revision", "incomplete", "cannot edit"):
            self.assertIn(marker.lower(), (main + reviewers).lower())
        for marker in ("evidence-locator", "chemistry-comparability", "synthesis-rebuttal", "overclaim-counterexample"):
            self.assertIn(marker, reviewers)
        for marker in ("claim", "paragraph", "locator", "severity", "rationale", "confidence", "earliest return stage", "suggested action"):
            self.assertIn(marker.lower(), reviewers.lower())
        for marker in ("conflict", "incomplete", "review-report", "qa-plan", "revision-plan", "not pass/fail"):
            self.assertIn(marker.lower(), arbiter.lower())
        for marker in ("accept", "reject", "defer", "Intent", "Research", "Synthesis", "ordinary language", "does not automatically"):
            self.assertIn(marker.lower(), routing.lower())

    def test_framework_documents_cover_generalized_judgment_and_non_comparability(self):
        skill = CANONICAL / "chemical-review-framework"
        main = (skill / "SKILL.md").read_text(encoding="utf-8")
        intake = (skill / "intake-and-spine.md").read_text(encoding="utf-8")
        cases = (skill / "cases-and-comparison.md").read_text(encoding="utf-8")
        judgment = (skill / "judgment-and-boundaries.md").read_text(encoding="utf-8")
        handoff = (skill / "handoff-and-revision.md").read_text(encoding="utf-8")
        combined = "\n".join((main, intake, cases, judgment, handoff)).lower()
        for marker in (
            "confirmed brief",
            "research handoff",
            "allowlist",
            "mineru",
            "evidence matrix",
            "case cards",
            "comparison map",
            "judgment framework",
            "framework handoff",
            "source identity",
            "locator",
            "judgment-changing",
            "not_comparable",
            "unknown",
            "no defensible framework",
            "testable",
            "alternative explanation",
            "applicability boundary",
        ):
            self.assertIn(marker, combined)
        for marker in ("system", "variable", "context", "comparator", "endpoint", "limitation", "confounder"):
            self.assertIn(marker, intake.lower())
        for marker in ("agreement", "contradiction", "extension", "replication", "boundary"):
            self.assertIn(marker, cases.lower())
        for marker in ("evidence map", "research typology", "local explanation", "chemical gap"):
            self.assertIn(marker, judgment.lower())

    def test_framework_preserves_ownership_and_trusted_mineru_boundary(self):
        skill = CANONICAL / "chemical-review-framework"
        main = (skill / "SKILL.md").read_text(encoding="utf-8").lower()
        intake = (skill / "intake-and-spine.md").read_text(encoding="utf-8").lower()
        handoff = (skill / "handoff-and-revision.md").read_text(encoding="utf-8").lower()
        for marker in (
            "trusted source text",
            "stable identity",
            "auditable locator",
            "parser-excerpt",
            "does not prove",
            "research owns",
            "framework owns",
            "synthesis reads",
            "do not silently rewrite",
            "research gap",
            "return to research",
            "same conversation",
            "independent entry",
        ):
            self.assertIn(marker, main + intake + handoff)

    def test_publication_documents_define_clean_projection_and_docx_boundary(self):
        skill = CANONICAL / "chemical-review-publication"
        main = (skill / "SKILL.md").read_text(encoding="utf-8")
        clean = (skill / "clean-projection.md").read_text(encoding="utf-8")
        journal = (skill / "journal-and-visuals.md").read_text(encoding="utf-8")
        docx = (skill / "docx-and-boundary.md").read_text(encoding="utf-8")
        combined = "\n".join((main, clean, journal, docx)).lower()
        for marker in (
            "draft.md",
            "journal-manuscript.md",
            "journal-manuscript.docx",
            "user-invoked",
            "one-time projection",
            "canonical",
            "allowlist",
            "mineru",
            "qa routing",
            "evidence id",
            "ordinary scientific language",
            "limitations",
            "model hypothesis",
            "no new literature",
            "no unsupported",
            "target journal",
            "official guidance",
            "confirmation",
            "language",
            "translation",
            "source-linked",
            "ambiguous",
            "openable",
        ):
            self.assertIn(marker, combined)
        for marker in ("does not mutate", "second", "source of truth", "pre-qa", "journalized draft"):
            self.assertIn(marker, docx.lower() + main.lower())

    def test_publication_preserves_science_while_removing_process_metadata(self):
        skill = CANONICAL / "chemical-review-publication"
        clean = (skill / "clean-projection.md").read_text(encoding="utf-8").lower()
        journal = (skill / "journal-and-visuals.md").read_text(encoding="utf-8").lower()
        for marker in (
            "source_fact",
            "model_synthesis",
            "model_hypothesis",
            "unknown",
            "not_comparable",
            "chemical gap",
            "partial-scope",
            "evidence boundary",
            "do not delete",
            "do not change",
            "figures",
            "schemes",
            "tables",
            "caption",
            "locator",
            "citation",
        ):
            self.assertIn(marker, clean + journal)

    def test_framework_product_use_fixture_covers_comparison_conflict_and_domain_variants(self):
        framework = FIXTURE / "framework"
        compatible = (framework / "evidence-matrix-compatible.md").read_text(encoding="utf-8")
        domains = (framework / "domain-modules.md").read_text(encoding="utf-8")
        cases = (framework / "case-cards.md").read_text(encoding="utf-8")
        comparison = (framework / "comparison-map.md").read_text(encoding="utf-8")
        for marker in (
            "confirmed brief",
            "stable identity",
            "system",
            "variable/intervention",
            "context",
            "comparator",
            "endpoint and denominator",
            "locator",
            "limitation/confounder",
            "applicability boundary",
            "TRUSTED_SOURCE_TEXT",
            "SOURCE_OBSERVATION",
            "VERIFIED_SOURCE_FACT",
            "MODEL_SYNTHESIS",
            "MODEL_HYPOTHESIS",
            "UNKNOWN",
        ):
            self.assertIn(marker.lower(), compatible.lower())
        for marker in (
            "organic synthesis",
            "substrate class",
            "materials chemistry",
            "processing history",
            "analytical chemistry",
            "calibration",
            "medicinal or chemical biology",
            "no global hard schema",
        ):
            self.assertIn(marker.lower(), domains.lower())
        for marker in (
            "clear matched control",
            "conflicting result",
            "negative result",
            "independent repeat",
            "alternative",
            "next test",
            "limitation",
        ):
            self.assertIn(marker.lower(), cases.lower())
        for marker in ("agreement", "contradiction", "extension", "replication", "boundary", "NOT_COMPARABLE"):
            self.assertIn(marker.lower(), comparison.lower())

    def test_framework_product_use_fixture_handles_no_common_endpoint_and_insufficient_evidence(self):
        framework = FIXTURE / "framework"
        no_common = (framework / "no-common-endpoint.md").read_text(encoding="utf-8").lower()
        insufficient = (framework / "insufficient-evidence.md").read_text(encoding="utf-8").lower()
        judgment = (framework / "judgment-framework.md").read_text(encoding="utf-8").lower()
        handoff = (framework / "framework-handoff.md").read_text(encoding="utf-8").lower()
        for marker in (
            "evidence map",
            "research typology",
            "local explanation chain",
            "not_comparable",
            "chemical gap",
            "no unified ranking",
        ):
            self.assertIn(marker, no_common)
        for marker in (
            "no defensible framework",
            "research evidence gap",
            "extraction gap",
            "earliest targeted research action",
            "stable identity",
            "original pdf",
            "source_fact",
        ):
            self.assertIn(marker, insufficient)
        for marker in (
            "central judgment",
            "support",
            "counterexample",
            "alternative explanation",
            "applicability boundary",
            "testable question",
            "explanation chain",
            "chemical gap",
        ):
            self.assertIn(marker, judgment)
        for marker in (
            "inputs",
            "completed",
            "reusable",
            "boundaries",
            "researcher decision",
            "next recommendation",
            "stage result summary",
        ):
            self.assertIn(marker, handoff)

    def test_publication_product_use_fixture_cleans_metadata_and_preserves_science(self):
        publication = FIXTURE / "publication"
        draft = (publication / "draft.md").read_text(encoding="utf-8")
        manuscript = (publication / "journal-manuscript.md").read_text(encoding="utf-8")
        draft_lower = draft.lower()
        manuscript_lower = manuscript.lower()
        for marker in (
            "mineru parser status",
            "4 pdf attachments",
            "qa routing",
            "evidence id",
            "stage/unit",
            "source_fact",
            "model_synthesis",
            "model_hypothesis",
            "unknown",
            "not_comparable",
            "chemical gap",
            "partial-scope",
        ):
            self.assertIn(marker.lower(), draft_lower)
        for marker in (
            "mineru",
            "pdf attachments",
            "qa routing",
            "evidence id",
            "stage/unit",
            "source_fact",
            "model_synthesis",
            "model_hypothesis",
        ):
            self.assertNotIn(marker.lower(), manuscript_lower)
        for marker in (
            "42% to 78%",
            "limited to the tested substrate class",
            "negative result",
            "cannot be ranked together",
            "not structurally assigned",
            "does not establish behavior",
            "hypothesis",
            "table",
            "figure 1",
            "references",
        ):
            self.assertIn(marker.lower(), manuscript_lower)
        self.assertIn("partial-scope", draft_lower)
        self.assertNotIn("partial-scope", manuscript_lower)
        self.assertIn("current review does not establish", manuscript_lower)
        doi_pattern = r"doi:10\.0000/fixture-[a-z]"
        self.assertEqual(
            set(re.findall(doi_pattern, draft_lower)),
            set(re.findall(doi_pattern, manuscript_lower)),
            "Publication fixture must not add or drop literature identities",
        )

    def test_synthesis_plan_uses_topic_appropriate_explanation_evidence(self):
        planning = (CANONICAL / "chemical-review-synthesis" / "planning.md").read_text(encoding="utf-8").lower()
        self.assertIn("适合该主题的解释证据", planning)
        self.assertIn("只有在 brief 需要时才使用“机制”术语", planning)

    def test_publication_product_use_fixture_covers_visuals_journal_branches_and_docx_boundary(self):
        publication = FIXTURE / "publication"
        visuals = (publication / "visual-assets.md").read_text(encoding="utf-8").lower()
        neutral = (publication / "neutral-path.md").read_text(encoding="utf-8").lower()
        target = (publication / "target-journal.md").read_text(encoding="utf-8").lower()
        docx = (publication / "docx-acceptance.md").read_text(encoding="utf-8").lower()
        for marker in (
            "retain figure 1",
            "source identity",
            "caption",
            "locator",
            "citation",
            "exclude figure 2",
            "cross-paper composite",
            "no new visual",
        ):
            self.assertIn(marker, visuals)
        for marker in ("no target journal", "neutral review-article structure", "no claim", "official rule"):
            self.assertIn(marker, neutral)
        for marker in ("target journal", "must ask", "confirmation", "official author instructions", "access date"):
            self.assertIn(marker, target)
        for marker in (
            "journal-manuscript.docx",
            "exact inspected",
            "opens as a real word document",
            "title",
            "table",
            "references",
            "uncertainty",
            "not_comparable",
            "partial-scope",
            "does not claim",
            "cannot generate or open docx",
            "second source of truth",
        ):
            self.assertIn(marker, docx)

    def test_publication_product_use_fixture_preserves_input_language_without_translation(self):
        language = (FIXTURE / "publication" / "language-preservation.md").read_text(encoding="utf-8")
        for marker in ("Translation was not requested", "中文", "配体 L1", "催化剂状态", "孤立收率", "must not silently translate"):
            self.assertIn(marker, language)
        self.assertIn("在限定的催化剂状态与底物范围内", language)
        self.assertIn("A separate, explicitly confirmed translation task", language)

    def test_plugin_manifest_and_projection_are_document_first(self):
        manifest = json.loads(
            (ROOT / "plugins" / "chemical-review" / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["skills"], "./skills/")
        description = manifest["interface"]["longDescription"].lower()
        self.assertIn("markdown", description)
        self.assertNotIn("retained scripts", description)
        self.assertIn("framework", description)
        self.assertIn("publication", description)
        prompts = " ".join(manifest["interface"]["defaultPrompt"]).lower()
        self.assertIn("chemical-review-framework", prompts)
        self.assertIn("chemical-review-publication", prompts)

    def test_fresh_project_acceptance_runbook_covers_public_boundary_and_layered_claims(self):
        runbook = (ROOT / "docs" / "v2-fresh-project-acceptance.md").read_text(encoding="utf-8")
        report = (ROOT / "docs" / "v2-acceptance-report.md").read_text(encoding="utf-8")
        for marker in (
            "topic-only",
            "framework",
            "evidence-matrix",
            "case-cards",
            "comparison-map",
            "judgment-framework",
            "configure_and_continue",
            "formal Research start",
            "candidate",
            "legal download request",
            "SOURCE_EXCERPT",
            "VERIFIED_SOURCE_FACT",
            "synthesis-plan.md",
            "draft.md",
            "Incomplete QA",
            "earliest affected stage",
            "pressure",
            "Product Use",
            "HUMAN_ACCEPTANCE",
            "scientific validity",
            "journal acceptance",
            "journal-manuscript.md",
            "journal-manuscript.docx",
            "target journal",
            "projection",
        ):
            self.assertIn(marker.lower(), runbook.lower())
        self.assertIn("v2-fresh-project-acceptance.md", report)

    def test_fresh_project_acceptance_result_records_observed_fixture_run_and_limits_claims(self):
        result = (ROOT / "docs" / "v2-fresh-project-acceptance-result-20260825.md").read_text(encoding="utf-8")
        report = (ROOT / "docs" / "v2-acceptance-report.md").read_text(encoding="utf-8")
        for marker in (
            "controlled fixture",
            "Public entrypoints read",
            "configure_and_continue",
            "Incomplete QA",
            "OBSERVED — CONTROLLED FIXTURE",
            "HUMAN_ACCEPTANCE",
            "Scientific validity",
            "Journal acceptance",
            "does not replace",
        ):
            self.assertIn(marker.lower(), result.lower())
        self.assertIn("OBSERVED — CONTROLLED FIXTURE", report)

    def test_committed_fresh_project_fixture_contains_advisory_two_step_evidence(self):
        fixture = ROOT / "tests" / "fixtures" / "v2-fresh-project"
        self.assertTrue((fixture / "intent" / "advisory-findings.md").is_file())
        proposal = (fixture / "intent" / "review-brief.proposed.md").read_text(encoding="utf-8")
        before = (fixture / "intent" / "review-brief.before-advisory.md").read_text(encoding="utf-8")
        after = (fixture / "intent" / "review-brief.after-second-confirmation.md").read_text(encoding="utf-8")
        result = (fixture / "intent-result.md").read_text(encoding="utf-8")
        for marker in ("UNCONFIRMED_PROPOSAL", "second explicit confirmation", "canonical", "snapshot"):
            self.assertIn(marker.lower(), (proposal + before + after + result).lower())
        self.assertIn("opt-in", result.lower())
        self.assertIn("SOURCE_EXCERPT", (fixture / "research" / "evidence-ledger.md").read_text(encoding="utf-8"))
        self.assertIn("Incomplete QA", (fixture / "qa" / "review-report.md").read_text(encoding="utf-8"))
        for path, marker in (
            ("intent/advisory-reject-all.md", "reject all"),
            ("intent/advisory-defer.md", "deferred"),
            ("intent/advisory-timeout.md", "ADVISORY_TIMEOUT"),
            ("intent/advisory-malformed.md", "ADVISORY_MALFORMED"),
            ("research/preflight-failure.md", "failure"),
            ("research/candidate-return.md", "return_to_discovery"),
            ("research/ambiguous-binding.md", "UNKNOWN identity"),
        ):
            self.assertIn(marker.lower(), (fixture / path).read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
