# Research Evidence & Handoff

只把研究者接受的相关候选带入全文路线。对每篇全文，说明来源 identity、访问依据、文件位置、关联的 core claim 和下一步。

公开、直接且授权清楚的 PDF 可以协助下载；需要登录、机构权限、验证码或授权不明的来源，写一份 `research/download-requests.md`，给出合法 landing/download URL、建议文件名、`research/inbox/authorized-pdfs/` 位置、受影响论点和等待动作。凭据、cookie 和 signed URL 不进入文档。

MinerU 或其它解析结果先作为阅读摘录：

```text
SOURCE_EXCERPT [identity @ page/section locator]: excerpt
```

研究者对照原始 PDF 后，再把直接支持的句子写成：

```text
VERIFIED_SOURCE_FACT [identity @ page/section locator]: claim
```

缺失或无法比较的地方保留 `UNKNOWN`、`NOT_COMPARABLE` 或 `Chemical GAP`，并把它们与受影响的论点连起来。

## Handoff

`research/research-handoff.md` 用短摘要说明候选与检索覆盖、可用全文和 locator、仍缺的证据、不可比较处、是否只能做 partial-scope Synthesis，以及推荐下一步。可以使用 `READY_FOR_SYNTHESIS`、`WAITING_FOR_USER` 或 `RESEARCH_GAP` 作为醒目标记，但解释比标签更重要。

把 handoff 给研究者看，等待 `accept_research_handoff` 或普通语言确认；若要补证据就保留旧文档和反馈，返回 Discovery 或全文路线。完成本页的标准是：下一位作者能看懂证据够在哪里、不够在哪里、为什么，以及应该先做什么。
