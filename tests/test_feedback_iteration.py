from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "chemical-review"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "chemical-review"
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(ROOT / "tests"))

from orchestrator import ChemicalReviewOrchestrator, _replace_frontmatter  # noqa: E402


class FeedbackIterationTests(unittest.TestCase):
    def test_feedback_fixtures_cover_the_iteration_contract(self):
        required = {
            "feedback-routing.md": ("intent", "Research", "delivery"),
            "feedback-intent-confirmation.md": ("explicit confirmation", "intent_revision"),
            "feedback-human-edit-conflict.md": ("human edit", "conflict"),
            "feedback-partial-rerun.md": ("partial rerun", "preserved"),
            "feedback-cold-restart.md": ("cold restart", "next_action"),
            "feedback-repeated-improvement.md": ("iteration", "revision"),
        }
        for filename, terms in required.items():
            text = (FIXTURE_DIR / filename).read_text(encoding="utf-8")
            for term in terms:
                self.assertIn(term, text)

    def test_routes_feedback_to_each_earliest_phase(self):
        cases = {
            "研究问题和范围已经变了": ("INTENT", "GRILL"),
            "补充缺失论文、定义和证据": ("RESEARCH", "RESEARCH"),
            "这里仍然只是摘要复述，需要比较和机制解释": ("PROTOTYPE", "PROTOTYPE"),
            "章节结构和叙事主线需要重做": ("PRD", "PRD"),
            "这个 unit 的 dependency 没有满足": ("ISSUES", "ISSUES"),
            "合并 section draft 到内容源": ("IMPLEMENT", "IMPLEMENT"),
            "Review 的化学推理和 claim status 有问题": ("REVIEW", "REVIEW"),
            "clean manuscript 的格式和研究版同步有问题": ("DELIVERY", "REVIEW"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                with TemporaryDirectory() as project_dir:
                    orchestrator = ChemicalReviewOrchestrator(project_dir)
                    orchestrator.start("nickel catalysis")
                    result = orchestrator.record_feedback(text)
                    self.assertEqual(result.assets["feedback_category"], expected[0])
                    self.assertEqual(result.assets["feedback_earliest_phase"], expected[1])

    def test_intent_feedback_waits_for_confirmation_and_preserves_original_intent(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("photocatalytic nitrogen fixation")
            pending = orchestrator.record_feedback("把研究问题改成气相和液相的对比")

            self.assertEqual(pending.status, "WAITING_FOR_HUMAN")
            self.assertEqual(pending.intent_confirmation, "REQUIRED")
            self.assertEqual(pending.human_action, "REQUIRED")
            self.assertEqual(pending.assets["feedback_earliest_phase"], "GRILL")
            intent = Path(project_dir, "review-intent.md").read_text(encoding="utf-8")
            self.assertIn("photocatalytic nitrogen fixation", intent)
            self.assertIn("Core-claim candidates", intent)
            self.assertIn("Pending intent feedback", intent)

            confirmed = orchestrator.confirm_feedback(accept=True)
            self.assertEqual(confirmed.status, "ACTIVE")
            self.assertEqual(confirmed.intent_revision, 1)
            self.assertEqual(confirmed.phase, "GRILL")
            self.assertIn("Confirmed intent feedback", Path(project_dir, "review-intent.md").read_text(encoding="utf-8"))

    def test_rejecting_intent_feedback_restores_previous_confirmation_state(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("nickel catalysis")
            orchestrator.record_feedback("把范围扩展到钴催化体系")

            rejected = orchestrator.confirm_feedback(accept=False)

            self.assertEqual(rejected.phase, "GRILL")
            self.assertEqual(rejected.intent_confirmation, "REQUIRED")
            self.assertNotIn(
                "Pending intent feedback",
                Path(project_dir, "review-intent.md").read_text(encoding="utf-8"),
            )

    def test_rejected_intent_feedback_is_not_rerouted_after_cold_restart(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("nickel catalysis")
            orchestrator._write(
                Path(project_dir, "workflow-state.md"),
                _replace_frontmatter(
                    Path(project_dir, "workflow-state.md").read_text(encoding="utf-8"),
                    {
                        "phase": "REVIEW",
                        "status": "CANDIDATE_READY",
                        "intent_confirmation": "CONFIRMED",
                    },
                ),
            )
            orchestrator.record_feedback("把研究问题改成钴催化体系")
            orchestrator.confirm_feedback(accept=False)

            resumed = ChemicalReviewOrchestrator(project_dir).resume_cycle()

            self.assertEqual(resumed.phase, "REVIEW")
            self.assertNotEqual(resumed.phase, "GRILL")

    def test_direct_manuscript_edit_is_preserved_and_conflict_is_surfaced(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("nickel catalysis")
            edited = "# Human edited manuscript\n\nKeep this paragraph exactly."

            result = orchestrator.record_feedback(
                "我直接修改了正文，请合并并检查",
                edited_manuscript=edited,
                base_source_digest="stale-digest",
            )

            self.assertEqual(result.assets["feedback_category"], "IMPLEMENT")
            self.assertEqual(result.status, "WAITING_FOR_HUMAN")
            self.assertEqual(result.human_action, "REQUIRED")
            edit_files = tuple((Path(project_dir) / "human-edits").glob("*.md"))
            self.assertEqual(len(edit_files), 1)
            self.assertIn(edited, edit_files[0].read_text(encoding="utf-8"))
            feedback = Path(project_dir, "review-feedback.md").read_text(encoding="utf-8")
            self.assertIn("CONFLICT", feedback)
            self.assertIn("stale-digest", feedback)

    def test_partial_rerun_preserves_existing_research_and_blueprint_assets(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("nickel catalysis")
            orchestrator._write(
                Path(project_dir, "workflow-state.md"),
                _replace_frontmatter(
                    Path(project_dir, "workflow-state.md").read_text(encoding="utf-8"),
                    {"phase": "REVIEW", "status": "CANDIDATE_READY"},
                ),
            )
            research = Path(project_dir, "research-evidence.md")
            blueprint = Path(project_dir, "review-blueprint.md")
            research.write_text("RESEARCH SENTINEL", encoding="utf-8")
            blueprint.write_text("BLUEPRINT SENTINEL", encoding="utf-8")

            routed = orchestrator.record_feedback("补充最新论文和定义后重新研究")
            resumed = ChemicalReviewOrchestrator(project_dir).resume()

            self.assertEqual(routed.assets["feedback_earliest_phase"], "RESEARCH")
            self.assertEqual(resumed.phase, "RESEARCH")
            self.assertEqual(research.read_text(encoding="utf-8"), "RESEARCH SENTINEL")
            self.assertEqual(blueprint.read_text(encoding="utf-8"), "BLUEPRINT SENTINEL")
            self.assertIn("preserving", resumed.next_action.lower())

    def test_feedback_survives_cold_restart_and_repeated_cycles_append_history(self):
        with TemporaryDirectory() as project_dir:
            first = ChemicalReviewOrchestrator(project_dir)
            first.start("nickel catalysis")
            first.record_feedback("Review 需要更强的趋势解释")
            second = ChemicalReviewOrchestrator(project_dir)
            second.record_feedback("期刊格式和 clean manuscript 需要同步")
            resumed = ChemicalReviewOrchestrator(project_dir).resume()

            self.assertEqual(resumed.assets["feedback_revision"], "2")
            self.assertEqual(resumed.assets["feedback_earliest_phase"], "REVIEW")
            feedback = Path(project_dir, "review-feedback.md").read_text(encoding="utf-8")
            self.assertIn("Feedback 1", feedback)
            self.assertIn("Feedback 2", feedback)
            self.assertIn("next_action", feedback)
            self.assertEqual(feedback.count("# Review Feedback Log"), 1)

    def test_review_delivery_feedback_reruns_only_the_review_tail(self):
        with TemporaryDirectory() as project_dir:
            from test_review_delivery import ReviewDeliveryTests

            review_fixture = ReviewDeliveryTests()
            orchestrator = review_fixture._review_ready_project(project_dir)
            assessment = review_fixture._assessment()
            journal = review_fixture._journal_adaptation()
            orchestrator.run_review(assessment, journal)
            content_before = Path(project_dir, "review-content.md").read_text(encoding="utf-8")

            routed = orchestrator.record_feedback("clean manuscript 的格式和研究版同步有问题")
            rerun = orchestrator.resume_cycle(
                review_assessment=assessment,
                journal_adaptation=journal,
            )

            self.assertEqual(routed.assets["feedback_category"], "DELIVERY")
            self.assertEqual(rerun.phase, "REVIEW")
            self.assertEqual(rerun.status, "CANDIDATE_READY")
            self.assertEqual(
                Path(project_dir, "review-content.md").read_text(encoding="utf-8"),
                content_before,
            )
            self.assertTrue(
                Path(project_dir, "review-history", "feedback-1", "clean-manuscript.md").exists()
            )
            self.assertTrue(Path(project_dir, "clean-manuscript.md").exists())

    def test_feedback_record_rolls_back_log_edit_intent_and_state_on_failure(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("nickel catalysis")
            state_path = Path(project_dir, "workflow-state.md")
            intent_path = Path(project_dir, "review-intent.md")
            original_state = state_path.read_text(encoding="utf-8")
            original_intent = intent_path.read_text(encoding="utf-8")

            def fail_after_partial_state_write(**_updates):
                state_path.write_text("partial state", encoding="utf-8")
                raise OSError("simulated feedback state failure")

            with patch.object(orchestrator, "_update_state", new=fail_after_partial_state_write):
                with self.assertRaisesRegex(OSError, "feedback state failure"):
                    orchestrator.record_feedback(
                        "把研究问题改成新的催化体系",
                        edited_manuscript="# Human edit",
                    )

            self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)
            self.assertEqual(intent_path.read_text(encoding="utf-8"), original_intent)
            self.assertFalse(Path(project_dir, "review-feedback.md").exists())
            self.assertFalse(tuple((Path(project_dir) / "human-edits").glob("*.md")))

    def test_confirm_feedback_rolls_back_intent_and_state_on_failure(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("nickel catalysis")
            orchestrator.record_feedback("把研究问题改成新的催化体系")
            state_path = Path(project_dir, "workflow-state.md")
            intent_path = Path(project_dir, "review-intent.md")
            original_state = state_path.read_text(encoding="utf-8")
            original_intent = intent_path.read_text(encoding="utf-8")

            with patch.object(
                orchestrator,
                "_update_state",
                side_effect=OSError("simulated confirmation state failure"),
            ):
                with self.assertRaisesRegex(OSError, "confirmation state failure"):
                    orchestrator.confirm_feedback(accept=True)

            self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)
            self.assertEqual(intent_path.read_text(encoding="utf-8"), original_intent)

    def test_review_archive_failure_restores_all_old_delivery_outputs_and_state(self):
        with TemporaryDirectory() as project_dir:
            from test_review_delivery import ReviewDeliveryTests

            review_fixture = ReviewDeliveryTests()
            orchestrator = review_fixture._review_ready_project(project_dir)
            assessment = review_fixture._assessment()
            journal = review_fixture._journal_adaptation()
            orchestrator.run_review(assessment, journal)
            old_outputs = {
                name: Path(project_dir, name).read_text(encoding="utf-8")
                for name in (
                    "clean-manuscript.md",
                    "researcher-review.md",
                    "review-report.md",
                    "submission-candidate-package.md",
                )
            }
            orchestrator.record_feedback("clean manuscript 的格式和研究版同步有问题")
            original_state = Path(project_dir, "workflow-state.md").read_text(encoding="utf-8")

            with patch("shutil.move", side_effect=OSError("simulated archive failure")):
                with self.assertRaisesRegex(OSError, "archive failure"):
                    orchestrator.resume_cycle(
                        review_assessment=assessment,
                        journal_adaptation=journal,
                    )

            self.assertEqual(
                Path(project_dir, "workflow-state.md").read_text(encoding="utf-8"),
                original_state,
            )
            for name, content in old_outputs.items():
                self.assertEqual(Path(project_dir, name).read_text(encoding="utf-8"), content)

    def test_direct_edit_without_digest_is_a_conflict(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("nickel catalysis")

            result = orchestrator.record_feedback("请合并这个人工正文编辑", edited_manuscript="# Human edit")

            self.assertEqual(result.assets["feedback_conflict"], "CONFLICT")

    def test_orphan_human_edit_is_never_overwritten(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("nickel catalysis")
            edit_dir = Path(project_dir, "human-edits")
            edit_dir.mkdir()
            orphan = edit_dir / "manuscript-edit-1.md"
            orphan.write_text("ORIGINAL HUMAN EDIT", encoding="utf-8")

            result = orchestrator.record_feedback(
                "请保留这个人工修改",
                edited_manuscript="# New human edit",
            )

            self.assertEqual(result.assets["feedback_conflict"], "CONFLICT")
            self.assertEqual(orphan.read_text(encoding="utf-8"), "ORIGINAL HUMAN EDIT")
            self.assertEqual(len(tuple(edit_dir.glob("*.md"))), 2)

    def test_orphan_human_edit_survives_feedback_state_failure(self):
        with TemporaryDirectory() as project_dir:
            orchestrator = ChemicalReviewOrchestrator(project_dir)
            orchestrator.start("nickel catalysis")
            edit_dir = Path(project_dir, "human-edits")
            edit_dir.mkdir()
            orphan = edit_dir / "manuscript-edit-1.md"
            orphan.write_text("ORIGINAL HUMAN EDIT", encoding="utf-8")

            with patch.object(
                orchestrator,
                "_update_state",
                side_effect=OSError("simulated orphan rollback failure"),
            ):
                with self.assertRaisesRegex(OSError, "orphan rollback failure"):
                    orchestrator.record_feedback(
                        "请保留这个人工修改",
                        edited_manuscript="# New human edit",
                    )

            self.assertEqual(orphan.read_text(encoding="utf-8"), "ORIGINAL HUMAN EDIT")
            self.assertEqual(tuple(edit_dir.glob("*.md")), (orphan,))

    def test_repeated_same_feedback_revision_cannot_overwrite_review_history(self):
        with TemporaryDirectory() as project_dir:
            from test_review_delivery import ReviewDeliveryTests

            review_fixture = ReviewDeliveryTests()
            orchestrator = review_fixture._review_ready_project(project_dir)
            assessment = review_fixture._assessment()
            journal = review_fixture._journal_adaptation()
            orchestrator.run_review(assessment, journal)
            orchestrator.record_feedback("clean manuscript 的格式和研究版同步有问题")
            orchestrator.resume_cycle(review_assessment=assessment, journal_adaptation=journal)
            history_path = Path(project_dir, "review-history", "feedback-1", "clean-manuscript.md")
            history_before = history_path.read_text(encoding="utf-8")
            current_path = Path(project_dir, "clean-manuscript.md")
            current_path.write_text("HUMAN MODIFIED CURRENT DELIVERY", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "review history already exists"):
                orchestrator.resume_cycle(
                    review_assessment=assessment,
                    journal_adaptation=journal,
                )

            self.assertEqual(history_path.read_text(encoding="utf-8"), history_before)
            self.assertEqual(current_path.read_text(encoding="utf-8"), "HUMAN MODIFIED CURRENT DELIVERY")


if __name__ == "__main__":
    unittest.main()
