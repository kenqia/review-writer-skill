# Research Evidence & Handoff

只把研究者接受的相关候选带入全文路线。对每篇全文，说明来源 identity、访问依据、文件位置、版本、关联的 core claim、证据等级和下一步。Evidence ledger 是人类可读的记录，不是固定数据库 schema；它属于 Research，Synthesis 只能读取，不能静默改写。

公开、直接且授权清楚的 PDF 可以协助下载；需要登录、机构权限、验证码或授权不明的来源，按 [`full-text-and-resume.md`](full-text-and-resume.md) 写一份 `research/download-requests.md`，给出合法 landing/download URL、访问依据、建议文件名、`research/inbox/authorized-pdfs/` 位置、受影响论点和等待动作。凭据、cookie 和 signed URL 不进入文档。

MinerU 或其它解析结果先作为阅读摘录：

```text
SOURCE_EXCERPT [identity @ page/section locator]: excerpt
```

研究者对照原始 PDF 后，再把直接支持的句子写成：

```text
VERIFIED_SOURCE_FACT [identity @ page/section locator]: claim
```

缺失或无法比较的地方保留 `UNKNOWN`、`NOT_COMPARABLE` 或 `Chemical GAP`，并把它们与受影响的论点连起来。Evidence ledger 还应保留版本、access basis、evidence level、limitation、locator、原始 PDF 核验状态以及 parser configuration probe 与 relevant-PDF per-run coverage 的区别。

## Coverage、stopping 与恢复

不要用固定论文数、query 数或 parser 成功次数宣布充分。Research handoff 应说明：已覆盖哪些 discovery path 和 core claim、每条路径带来的 marginal gain（边际新增价值）、重要未覆盖区域（uncovered areas）、不可访问/未解析/未核验来源、预算（budget）和 retry 影响，以及为何建议继续、缩小范围、暂停或停止当前轮。若新的 query 不再带来重要相关候选但仍有关键盲区，明确保留 `Chemical GAP`，不能把“接近饱和”写成科学穷尽。

中断时从 `research/progress.md`、download requests、candidate acceptance 和 evidence ledger 恢复，保留旧 handoff 和研究者决定；不得静默覆盖已有 verified fact 或把 `SOURCE_EXCERPT` 升级为事实。

## Handoff

`research/research-handoff.md` 用短摘要说明候选与检索覆盖、可用全文和 locator、仍缺的证据、不可比较处、是否只能做 partial-scope Synthesis，以及推荐下一步。可以使用 `READY_FOR_SYNTHESIS`、`WAITING_FOR_USER` 或 `RESEARCH_GAP` 作为醒目标记，但解释比标签更重要。

把 handoff 给研究者看，等待 `accept_research_handoff` 或普通语言确认；若要补证据就保留旧文档和反馈，返回 Discovery 或全文路线。完成本页的标准是：下一位作者能看懂证据够在哪里、不够在哪里、为什么，coverage/stopping 判断如何形成，以及应该先做什么。`READY_FOR_SYNTHESIS` 只表示研究者明确接受当前 handoff 的证据边界，不表示 scientific validity、journal acceptance 或完整性认证。
