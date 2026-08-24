---
name: chemical-review-synthesis
description: "Produce one evidence-bounded critical chemistry review draft from Intent and Research Markdown."
---

# Chemical Review Synthesis

独立入口：直接读取 `review-brief.md` 和 Research 的 `research-handoff.md`、`evidence-notes.md`、`comparability-matrix.md`，独占项目根目录唯一 `draft.md`，并从同一输入生成 `reader-draft.md` 与 `research-draft.md` 两个同步视图。三者都由 Synthesis 写入，不能各自独立演化。不构造旧 Prototype/PRD/unit payload，不使用 central merge。

正文必须区分 `SOURCE_FACT`、`MODEL_SYNTHESIS`、`MODEL_HYPOTHESIS`，保留 `UNKNOWN`、`NOT_COMPARABLE` 和 `Chemical GAP`。正文中的 `SOURCE_FACT` 必须对应 Research 中明确标记为 `VERIFIED_SOURCE_FACT [identity @ locator]: claim`、且已由人/Agent 对照原始 PDF 核验的证据；仅有 `SOURCE_EXCERPT` 或未标记的 `SOURCE_FACT` 不够。正文 claim 文本还必须出现在同一已核验证据行中。`RESEARCH_GAP` 下允许局部候选稿，但必须标记 `unreviewed; evidence-bounded; partial-scope`，不能补造缺失 SOURCE_FACT。

```bash
python synthesis.py --project /path/to/project --scaffold > candidate.md
python synthesis.py --project /path/to/project --candidate candidate.md
```

Synthesis 独占 `draft.md`；QA 只能读取并报告，不能改写它。
