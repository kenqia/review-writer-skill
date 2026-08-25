# Synthesis Drafting

以 `draft.md` 作为唯一 canonical 正文基线。读者版 `reader-draft.md` 和研究版 `research-draft.md` 都从同一 revision 基线整理，避免两个版本各自漂移；任何 human edit 先保留在 canonical draft 或 feedback 中，不由 projection 静默覆盖。

写重要段落时，让读者能分辨：

```text
SOURCE_FACT [identity @ locator]: 直接来自来源的事实
MODEL_SYNTHESIS: 跨来源的比较或解释
MODEL_HYPOTHESIS: 可以被后续证据检验的推断
```

重要 claim 适用时保留 source identity、locator、conditions、comparator、denominator/measurement basis 和 limitation。条件、对照、测量口径和机制证据不清楚时降低语气。把 UNKNOWN、NOT_COMPARABLE 和 Chemical GAP 写出来；不要用漂亮的数字、novelty 或 uniqueness 填补缺失全文。Research 只覆盖部分范围时，在稿件开头说明 `unreviewed; evidence-bounded; partial-scope`，并公开未覆盖区域和返回 Research/缩小范围建议。

研究者的反馈可以直接写在 `draft-feedback.md` 或 `qa/feedback.md`。保留旧稿，说明此次修改影响了哪条论点，必要时返回 Research 或 Intent。
