---
name: chemical-review-synthesis
description: "Produce one evidence-bounded critical chemistry review draft from Intent and Research Markdown."
---

# Chemical Review Synthesis

独立入口：直接读取 `review-brief.md` 和 Research 的 `research-handoff.md`、`evidence-notes.md`、`comparability-matrix.md`，独占项目根目录唯一 `draft.md`。不构造旧 Prototype/PRD/unit payload，不使用 central merge。

正文必须区分 `SOURCE_FACT`、`MODEL_SYNTHESIS`、`MODEL_HYPOTHESIS`，保留 `UNKNOWN`、`NOT_COMPARABLE` 和 `Chemical GAP`。`SOURCE_FACT` 必须对应 Research 中已由人/Agent 对照原始 PDF 核验的 locator；仅有 `SOURCE_EXCERPT` 不够。`RESEARCH_GAP` 下允许局部候选稿，但必须标记 `unreviewed; evidence-bounded; partial-scope`，不能补造缺失 SOURCE_FACT。

```bash
python synthesis.py --project /path/to/project --scaffold > candidate.md
python synthesis.py --project /path/to/project --candidate candidate.md
```

Synthesis 独占 `draft.md`；QA 只能读取并报告，不能改写它。
