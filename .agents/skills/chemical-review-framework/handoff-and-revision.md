# Framework handoff 与修订

Framework handoff 是人类可读的阶段结果摘要，不是额外的会话仪式，也不是隐藏的内部状态。它让 same conversation（同一会话）可以继续，也让独立重跑只凭持久化材料恢复。

## `framework-handoff.md` 应包含

- 本轮读取的 confirmed brief、Research handoff、文献/研究范围、MinerU 材料和额外 allowlist；
- 已完成的 evidence matrix、case cards、comparison map、judgment framework，以及没有生成的资产；
- 已形成的核心判断、解释链、反例、冲突和适用边界；
- `SOURCE_FACT`、`MODEL_SYNTHESIS`、`MODEL_HYPOTHESIS`、`UNKNOWN`、`NOT_COMPARABLE` 与 `Chemical GAP` 的重要分布；
- 证据范围、解析信任、locator、比较和推理的边界；
- 研究者已做的决定、待确认决定和最早的下一步；
- 建议进入 Synthesis、返回 Research、缩小范围、补 allowlist、暂停或结束本轮的理由。

可以使用 `READY_FOR_SYNTHESIS`、`RESEARCH_GAP`、`WAITING_FOR_USER` 等短标签，但每个标签都要用普通语言解释。`READY_FOR_SYNTHESIS` 只表示研究者接受当前证据边界，不表示科学有效性或期刊接收。

## Ownership 与 revision

Research handoff/evidence ledger、Framework 资产和 Synthesis `draft.md` 分属不同 owner。Research owns 来源和 evidence ledger，Framework owns 比较和判断资产，Synthesis reads 它们但不取得写权限。Framework 发现 Research 缺口时，在 handoff 中提出 return to Research 动作，不直接改写 Research ledger；Synthesis 发现比较问题时，提出回到 Framework 的修订，不直接覆盖案例卡。研究者拒绝、暂缓或改写一个判断时，保留旧版本或简短 revision snapshot，并说明最早受影响的阶段。

新一轮只读取当前 canonical 资产、必要旧快照和用户 allowlist。不要把完整对话复制进文档，也不要把旧稿、未确认建议或一段模型输出悄悄当成新事实。来源事实、模型综合和模型假设都可以被修订，但修订理由必须可读。

## 给下游的边界

Synthesis reads handoff 中哪些判断可以成为章节主轴、哪些只能写成局部观察、哪些仍是模型假设。若 Framework 被明确跳过，handoff 或 brief 应记录这一决定，Synthesis 必须降低完整性声明。Publication 只读取已确认稿件和 allowlist，不把 Framework handoff 原样带进普通期刊文本。

如果输入缺失、解析 identity/locator 不稳定、关键终点不可比较或本轮超出证据范围，保持 handoff 可读并报告原因；不要以“线索存在”冒充完成，也不要自动启动新的 Research 路线。
