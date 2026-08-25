# Intent Result And Revision

这份 companion 在 Intent 回合结束、需要跨会话恢复，或研究者要求修改既有 brief 时读取。它负责留下短而可读的阶段结果摘要（stage result summary）和有意义的 revision snapshot；不把对话全文倾倒进项目，也不把标签变成隐藏状态机。

## Stage result summary

在 `intent-result.md`（或项目明确指定的等价 Markdown 路径）中记录本轮：

1. 输入范围：本轮实际读取的 Intent 材料和用户 allowlist；
2. 已完成工作：哪些 frontier 问题已回答、哪些仍是 `UNKNOWN`，以及是否生成 draft/confirmed brief；
3. 可复用产物：当前 `review-brief.md`、`review-brief.proposed.md`、术语或 advisory 报告的路径；若 advisory 未运行、被跳过、被拒绝、暂缓或失败，也记录对应结果标签和报告位置；
4. 证据与推理边界：哪些是 `USER_ANSWER`、`DEFAULT`、`UNKNOWN` 或模型建议，哪些不能被下游当作来源事实；
5. 未解决问题与决定：研究者已接受、拒绝、暂缓的事项和冲突；advisory 的 opt-in、finding 选择、proposal confirmation 以及未决问题都要能恢复；
6. 下一步建议：继续哪一 frontier、是否等待用户、是否具备请求 Research formal start 的条件，以及需要的高影响确认。

摘要可以使用 `WAITING_FOR_USER`、`READY_FOR_RESEARCH` 或 `Chemical GAP` 等人类可读标签，但标签只是定位锚点。`READY_FOR_RESEARCH` 只有在 `review-brief.md` 已明确确认时才可使用；它不等于已经启动 Research。

brief advisory 的结果也要如实记录，例如 `ADVISORY_SKIPPED`、`ADVISORY_COMPLETE`、`ADVISORY_REJECTED`、`ADVISORY_DEFERRED`、`ADVISORY_TIMEOUT`、`ADVISORY_UNAVAILABLE` 或 `ADVISORY_MALFORMED`。失败或 malformed 输出必须说明原因和缺失字段，并保持 canonical brief unchanged；不能以“没有发现问题”替代 reviewer 缺失。

## Revision snapshot

每次会改变核心研究问题、scope、exclusions 或 evidence expectations 的新一轮，先保留当前 canonical brief 的 revision snapshot，并写一小段原因、触发的 earliest affected stage、最早 frontier、研究者修改和预期影响。快照可以放在项目约定的 `revisions/intent/` 目录，使用人类可读的 round/date/slug 命名；不要求固定字段或脚本生成。

新草案或 advisory proposal 写入 `review-brief.proposed.md`，并标注 `UNCONFIRMED_PROPOSAL`；确认前不得静默覆盖 `review-brief.md`（do not silently overwrite）。proposal 需要第二次明确 confirmation 才能更新 canonical brief，同时在 `intent-result.md` 指向旧快照和本轮决定。研究者的直接编辑、接受/拒绝/暂缓建议和 advisory failure reason 都要保留；不要用模型重写覆盖它们。

需要返回时，从最早受影响的阶段继续：核心意图变更回 Intent，单纯术语补充先修订 glossary，Research 尚未开始则不制造虚假的下游结果。若找不到当前 brief、摘要或用户要求的 allowlist，报告缺口并请求材料，不从上一段聊天或无关历史推断。

## 完成与非完成

Intent 回合只有在摘要说明了输入、工作、产物、边界、未决问题、决定和下一步，且研究者确认状态清楚时才可报告完成。暂停、用户未确认、advisory 失败、关键材料缺失或仍有未处理的核心 frontier 时，诚实报告 `WAITING_FOR_USER` / `UNKNOWN`；不要把线索、默认值或半成品声称成 confirmed brief。
