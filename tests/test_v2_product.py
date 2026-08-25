from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.plugin_boundary import V2_SKILL_FILES


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / ".agents" / "skills"
PLUGIN = ROOT / "plugins" / "chemical-review" / "skills"


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

    def test_research_documents_are_guidance_not_a_scripted_gate(self):
        skill = CANONICAL / "chemical-review-research"
        main = (skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("preflight.md", main)
        self.assertIn("discovery-and-screening.md", main)
        self.assertIn("evidence-and-handoff.md", main)
        self.assertIn("Markdown", main)
        self.assertIn("configure_and_continue", (skill / "preflight.md").read_text(encoding="utf-8"))
        self.assertIn("confirm_formal_start", (skill / "preflight.md").read_text(encoding="utf-8"))
        self.assertIn("accept_candidates", (skill / "discovery-and-screening.md").read_text(encoding="utf-8"))
        self.assertIn("SOURCE_EXCERPT", (skill / "evidence-and-handoff.md").read_text(encoding="utf-8"))
        self.assertNotIn("manifest.json", main)

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


if __name__ == "__main__":
    unittest.main()
