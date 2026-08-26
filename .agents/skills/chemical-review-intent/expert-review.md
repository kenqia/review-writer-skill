# Optional Brief Expert Review

这是 confirmed brief 之后的可选 brief-shape advisory，不是 Research、QA、同行评审、科学有效性认证或 journal acceptance prediction。它只挑战问题是否可回答、主张是否可争论以及证据边界是否清楚；它不能替研究者作决定。

## Opt-in and isolated input

主会话先展示当前已确认的 `review-brief.md`，并明确询问研究者是否运行 advisory。只有明确的 opt-in 才创建 fresh、隔离的 reviewer；`skip` 不创建 reviewer，`reject all` 和 `defer` 也都不产生 brief 变更。Reviewer 的输入包严格只有以下三类内容：

1. 本文件中的 role prompt；
2. 当前 confirmed brief（只读）；
3. 研究者在本轮消息中明确列出的 allowlisted material。

不得把父会话、hidden context、历史/memory、凭据、cookie、session、sibling checkout 或未列出的项目文件带入输入包。Reviewer 不浏览、不调用 provider、不读取额外来源、不互读其他 reviewer 报告，也不编辑、创建或覆盖任何项目 artifact。

```text
You are an independent chemistry literature-review brief reviewer. Review only the confirmed brief and the explicitly allowlisted material in this message. Focus on answerability, core-claim contestability, scope and exclusions, audience and contribution, evidence standards, terminology, comparison fields, boundary scenarios, primary-study eligibility, and journal fit. Return concise findings grouped by actionable brief module. Every finding must include a stable id, module, severity, rationale, suggested change, confidence, and unresolved questions. Preserve UNKNOWN, NOT_COMPARABLE, and Chemical GAP; do not invent source facts. Do not browse, call providers, inspect hidden context, read unlisted files, or edit files. This is advisory only, not formal peer review, scientific-validity certification, or a journal-acceptance prediction.
```

## Findings contract and researcher choices

Reviewer 输出必须是人类可读 Markdown（或等价的可审查文本），按 actionable brief module 分组，而不是一串没有定位的意见。建议使用这些模块：`research question`、`core-claim candidates`、`scope/exclusions`、`audience/contribution`、`evidence expectations`，以及确实影响路线时的 `terminology/comparison fields`、`boundary scenarios`、`primary-study eligibility` 和 `journal fit`。每条 finding 至少包含：

- `id` 与 `module`：方便研究者逐条选择和追踪；
- `severity`：`blocker`、`major`、`minor` 或 `info`，只描述 brief 风险，不是假装科学 pass/fail；
- `rationale`：为什么当前 brief 可能不可回答、不可比较或超出边界；
- `suggested change`：可直接改写的 brief 文字或需要补充的决定，不能偷偷代填用户答案；
- `confidence`：reviewer 对该建议的信心；
- `unresolved questions`：仍需研究者回答、保留为 `UNKNOWN` 或标记为 `Chemical GAP` 的问题。

主会话展示完整 findings 后，研究者可 `accept selected`（只选部分）、逐条改写后接受、`reject all` 或 `defer`；也可以在 reviewer 运行前选择 `skip`。普通的“看起来不错”不等于接受，也不等于确认 proposal。

## Unconfirmed proposal and second confirmation

接受的 finding 先写入 `review-brief.proposed.md`，并标记 `UNCONFIRMED_PROPOSAL`。Proposal 逐条保留 finding id、module、原 rationale、研究者采用的 suggested change、来源边界、被拒/暂缓项和 unresolved questions；它是可审阅的工作材料，不是新的 canonical brief。主会话展示 proposal 后，必须再次明确询问研究者是否将其合并到现有 confirmed brief；需要 a second explicit confirmation，只有这第二次明确确认才能更新 `review-brief.md`，并按 `result-and-revision.md` 保留 revision snapshot。任何未确认、拒绝或暂缓都不会静默改变 canonical brief。

## Failure and incomplete output

Advisory 必须有可报告的结果标签：`ADVISORY_SKIPPED`、`ADVISORY_COMPLETE`、`ADVISORY_REJECTED`、`ADVISORY_DEFERRED`、`ADVISORY_TIMEOUT`、`ADVISORY_UNAVAILABLE` 或 `ADVISORY_MALFORMED`。超时、服务不可用、allowlist 缺失或输出 malformed（例如缺少 module、severity、rationale、suggested change、confidence 或 unresolved questions）时，主会话 report the reason，说明具体原因和缺失部分，不猜补 findings，不把失败当成正面意见，不生成或合并 proposal，且保持 `review-brief.md` unchanged。是否重试或继续 Research 由研究者明确决定。

专家审查只检查 brief 的问题形状与研究边界，不补来源、不改稿、不替代后续 Research 或正式同行评审。
