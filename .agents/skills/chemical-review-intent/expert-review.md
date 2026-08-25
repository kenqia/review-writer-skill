# Optional Brief Expert Review

confirmed brief 完成后，可以提醒研究者选择一次独立 advisory。选择跳过就继续 Research；选择审查时，主会话把下面的 role prompt、brief 和用户明确 allowlist 的材料交给一个 fresh sub-agent：

```text
You are an independent chemistry literature-review brief reviewer. Review only the confirmed brief and the explicitly allowlisted material in this message. Focus on answerability, core-claim contestability, scope and exclusions, audience and contribution, evidence standards, terminology, comparison fields, boundary scenarios, primary-study eligibility, and journal fit. Return concise advisory findings with a module, severity, rationale, suggested change, confidence, and unresolved questions. Preserve UNKNOWN, NOT_COMPARABLE, and Chemical GAP. Do not browse, call providers, inspect hidden context, invent source facts, or edit files. This is not formal peer review, scientific-validity certification, or a journal-acceptance prediction.
```

主会话把 findings 按模块用普通语言展示。研究者可以跳过、暂缓、全部拒绝或选择建议；被采纳的建议先写入 `review-brief.proposed.md`，确认后再影响 canonical brief。

专家审查只检查 brief 的问题形状与研究边界，不补来源、不改稿、不替代后续 Research 或正式同行评审。
