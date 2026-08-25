# Research Full Text And Resume

这份 companion 在研究者接受候选集、预检完成且正式 Research start 已确认后读取。它只处理 accepted candidates 的全文路线、合法访问等待、来源绑定、解析摘录和可恢复进度；它不自动接受候选、不自动降级，也不把解析结果直接升级为 source fact。

## 合法全文路线

对每个 researcher-accepted candidate，先记录 stable identity、关联 core claim、当前可用的合法 landing/PDF URL、access basis、版本和目标文件位置。公开、直接且授权清楚的 PDF 可以协助下载到项目约定目录；不绕过登录、机构权限、验证码、robots、paywall 或 ambiguous authorization。

restricted、login-gated、institution-dependent 或授权不明的来源，写入 legal download request：`research/download-requests.md`（或等价 Markdown），至少包含：受影响 claim、stable identity、合法 landing/download URL、access basis、建议文件名、`research/inbox/authorized-pdfs/` 目标位置、等待的研究者动作和回来后 rerun 方式。不要把 credential-bearing URL、cookie、token 或 signed URL 写入任何 artifact。

## 用户 PDF 绑定

研究者放入 authorized PDF 后，按 DOI、PMID、版本、标题/作者/年份等稳定字段与 candidate 逐一比对。只有 identity 唯一匹配时才记录绑定；多个候选都可能匹配、版本关系不清、文件内容与 metadata 冲突时，标成 `UNKNOWN identity` / `WAITING_FOR_USER`，列出冲突并请求明确选择，不要猜测绑定。

每份绑定记录至少保留原始 PDF 文件名/位置、identity、版本、access basis、核验日期、关联 claim 和后续 locator 范围。文件名相同、下载成功或 parser 能打开文件都不是 identity 证明。

## 解析与证据升级

parser configuration probe（parser probe）只证明工具能处理一份受控 fixture；它必须与 relevant-PDF per-run coverage 分开记录。对每一份实际 accepted PDF，记录是否尝试解析、解析版本/配置、成功或失败、覆盖到的页/章节和剩余问题；probe 的成功不能增加 relevant-PDF coverage 数量。

解析文本一律先写成：

```text
SOURCE_EXCERPT [identity @ page/section/figure/table locator]: excerpt
```

只有主 agent 或研究者直接对照合法 original PDF（原始 PDF）、稳定 identity 和精确 locator，并确认句子确实被原文支持后，才可写成：

```text
VERIFIED_SOURCE_FACT [identity @ page/section/figure/table locator]: claim
```

metadata、abstract、snippet、二手引用和 parser excerpt 不能被 promotion 成 fact。字段缺失写 `UNKNOWN`，比较轴不足写 `NOT_COMPARABLE`，当前证据范围不能回答写 `Chemical GAP`；不要用模型常识补齐条件、单位、分母、机制或限制。

## 中断、预算与恢复

在 `research/progress.md`（或等价 Markdown）保留本轮已处理候选、待处理候选、失败原因、retry 次数、预算/时间影响、cache reuse、最后一次安全检查点和下一步动作。中断、超时或工具失败时保留已绑定文件和已有 evidence notes；重新开始先读取 progress、download requests 和 evidence ledger，再从未完成或需人工确认的最早项目继续。

不得因为某个 provider、parser 或 PDF 失败而自动换路线、扩大/缩小范围或宣布完成。研究者可以明确接受 explained degradation，之后在新的 Research round 中按新边界继续；否则保持 `WAITING_FOR_USER` 或 `RESEARCH_GAP`。

## 完成与非完成

本页完成表示：所有进入全文路线的 accepted candidates 都有清楚的 access/binding 状态，解析与 per-run coverage 分开，证据等级和 locator 边界可读，未完成项可恢复。只拿到一份 PDF、跑通一次 parser 或生成 excerpt，不等于全文研究完成或 source fact 已验证。
