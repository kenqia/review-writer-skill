"""Human-feedback routing and preservation for iterative review cycles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping

from orchestrator import _document, _split_frontmatter


@dataclass(frozen=True)
class FeedbackRoute:
    category: str
    earliest_phase: str
    reason: str
    requires_confirmation: bool = False


class FeedbackRouter:
    """Use broad semantic cues to choose a restart boundary, not a rigid form."""

    _RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        (
            "INTENT",
            "GRILL",
            (
                "研究问题",
                "research question",
                "scope",
                "范围",
                "排除",
                "exclusion",
                "audience",
                "目标期刊",
                "target journal",
            ),
        ),
        (
            "RESEARCH",
            "RESEARCH",
            ("论文", "文献", "定义", "证据", "paper", "literature", "source", "search"),
        ),
        (
            "PROTOTYPE",
            "PROTOTYPE",
            ("摘要复述", "比较", "机制", "假设", "summary", "comparison", "mechanism", "hypothesis"),
        ),
        (
            "PRD",
            "PRD",
            ("章节结构", "章节", "叙事主线", "蓝图", "outline", "chapter", "narrative", "blueprint"),
        ),
        (
            "ISSUES",
            "ISSUES",
            ("unit", "dependency", "前置", "任务拆分", "研究单元", "写作单元"),
        ),
        (
            "DELIVERY",
            "REVIEW",
            (
                "clean manuscript",
                "researcher",
                "格式",
                "同步",
                "候选包",
                "submission",
                "delivery",
                "journal format",
                "formatting",
                "author guide",
            ),
        ),
        (
            "REVIEW",
            "REVIEW",
            ("review", "化学推理", "claim status", "诚信", "hard stop", "科学完整性", "journal adaptation"),
        ),
        (
            "IMPLEMENT",
            "IMPLEMENT",
            ("合并", "内容源", "正文", "draft", "merge", "implement", "写作"),
        ),
    )

    def route(self, text: str, *, direct_edit: bool = False) -> FeedbackRoute:
        normalized = text.strip().lower()
        if not normalized and not direct_edit:
            raise ValueError("Feedback must contain ordinary-language text or a manuscript edit.")
        if direct_edit:
            return FeedbackRoute(
                "IMPLEMENT",
                "IMPLEMENT",
                "A direct manuscript edit must be reviewed and centrally merged before delivery.",
            )
        for category, phase, keywords in self._RULES:
            if any(keyword.lower() in normalized for keyword in keywords):
                return FeedbackRoute(
                    category,
                    phase,
                    f"Feedback matched the {category.lower()} concern and returns to {phase}.",
                    requires_confirmation=category == "INTENT",
                )
        return FeedbackRoute(
            "REVIEW",
            "REVIEW",
            "Unclassified feedback is retained for Review rather than silently discarded.",
        )


class FeedbackRecorder:
    """Append feedback and preserve direct edits without overwriting prior inputs."""

    feedback_filename = "review-feedback.md"

    def __init__(self, project_root: str | Path, *, today: date | None = None) -> None:
        self.project_root = Path(project_root)
        self.today = today or date.today()

    @property
    def feedback_path(self) -> Path:
        return self.project_root / self.feedback_filename

    def record(
        self,
        text: str,
        *,
        edited_manuscript: str | None = None,
        base_source_digest: str | None = None,
    ) -> tuple[FeedbackRoute, int, str]:
        route = FeedbackRouter().route(text, direct_edit=edited_manuscript is not None)
        previous_raw = (
            self.feedback_path.read_text(encoding="utf-8") if self.feedback_path.exists() else None
        )
        previous_metadata, previous_body = self._read_previous()
        revision = int(previous_metadata.get("feedback_revision", "0")) + 1
        current_digest = self._current_digest()
        supplied_digest = base_source_digest or _frontmatter_digest(edited_manuscript or "")
        conflict = bool(
            edited_manuscript is not None
            and (not supplied_digest or supplied_digest != current_digest)
        )
        edit_path: Path | None = None
        if edited_manuscript is not None:
            edit_dir = self.project_root / "human-edits"
            edit_dir.mkdir(exist_ok=True)
            edit_path = edit_dir / f"manuscript-edit-{revision}.md"
            if edit_path.exists():
                conflict = True
                suffix = 1
                while edit_path.exists():
                    edit_path = edit_dir / f"manuscript-edit-{revision}-conflict-{suffix}.md"
                    suffix += 1
            edit_metadata = {
                "kind": "preserved-human-manuscript-edit",
                "schema": "1",
                "feedback_revision": str(revision),
                "route_category": route.category,
                "base_source_digest": supplied_digest or current_digest or "UNKNOWN",
                "conflict_status": "CONFLICT" if conflict else "PRESERVED",
                "updated": self.today.isoformat(),
            }
            edit_path.write_text(
                _document(
                    edit_metadata,
                    "# Preserved Human Manuscript Edit\n\n"
                    "The following edit is retained verbatim for central review:\n\n"
                    + edited_manuscript,
                ),
                encoding="utf-8",
            )
        entry = (
            f"## Feedback {revision}\n\n"
            f"- Category: {route.category}\n"
            f"- Earliest phase: {route.earliest_phase}\n"
            f"- Reason: {route.reason}\n"
            f"- Conflict: {'CONFLICT' if conflict else 'NONE'}\n\n"
            f"- Base source digest: {supplied_digest or current_digest or 'UNKNOWN'}\n\n"
            "### Human feedback\n"
            f"{text.strip() or 'Direct manuscript edit supplied.'}\n\n"
        )
        if edited_manuscript is not None:
            entry += f"- Preserved edit: human-edits/{edit_path.name}\n\n"
        metadata: Mapping[str, str] = {
            "kind": "chemical-review-feedback-log",
            "schema": "1",
            "feedback_revision": str(revision),
            "feedback_category": route.category,
            "feedback_earliest_phase": route.earliest_phase,
            "feedback_requires_confirmation": "REQUIRED" if route.requires_confirmation else "NONE",
            "feedback_conflict": "CONFLICT" if conflict else "NONE",
            "feedback_next_action": "Confirm the intent feedback before downstream regeneration."
            if route.requires_confirmation
            else f"Resume from {route.earliest_phase} using preserved assets.",
            "updated": self.today.isoformat(),
        }
        previous_body = previous_body.strip()
        if previous_body.startswith("# Review Feedback Log"):
            previous_body = previous_body[len("# Review Feedback Log") :].lstrip()
        body = (previous_body.rstrip() + "\n\n" if previous_body else "") + entry
        try:
            self.feedback_path.write_text(
                _document(metadata, "# Review Feedback Log\n\n" + body), encoding="utf-8"
            )
        except Exception:
            if edit_path is not None:
                edit_path.unlink(missing_ok=True)
            if previous_raw is None:
                self.feedback_path.unlink(missing_ok=True)
            else:
                self.feedback_path.write_text(previous_raw, encoding="utf-8")
            raise
        return route, revision, "CONFLICT" if conflict else "NONE"

    def latest(self) -> dict[str, str]:
        metadata, _ = self._read_previous()
        if not metadata:
            raise FileNotFoundError("No review-feedback.md has been recorded.")
        return metadata

    def _read_previous(self) -> tuple[dict[str, str], str]:
        if not self.feedback_path.exists():
            return {}, ""
        return _split_frontmatter(self.feedback_path.read_text(encoding="utf-8"))

    def _current_digest(self) -> str:
        clean = self.project_root / "clean-manuscript.md"
        if not clean.exists():
            return ""
        metadata, _ = _split_frontmatter(clean.read_text(encoding="utf-8"))
        return metadata.get("source_digest", "")


def _frontmatter_digest(text: str) -> str:
    if not text.startswith("---\n"):
        return ""
    try:
        metadata, _ = _split_frontmatter(text)
    except ValueError:
        return ""
    return metadata.get("source_digest", "")
