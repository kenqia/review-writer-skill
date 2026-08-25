---
name: chemical-review-research
description: "Discover sources, route legal full text, and prepare a human-readable chemistry evidence handoff."
---

# Chemical Review Research

Research 是一个文档型证据工作台。读取已确认的 `review-brief.md`，再按需要加载本目录的三份 companion：

1. [`preflight.md`](preflight.md)：快速了解当前网络、检索、全文和解析能力；
2. [`discovery-and-screening.md`](discovery-and-screening.md)：围绕 brief 找候选、去重、解释取舍；
3. [`evidence-and-handoff.md`](evidence-and-handoff.md)：记录合法全文、locator、证据笔记和下一步。

## 推荐节奏

- 先把能力检查写成一张人类可读的表，说明通过、缺失、影响、官方配置入口和回来后的动作。`configure_and_continue` 是“我去配置后回来”的选择；配置完成后再单独询问是否正式开始。
- 用短检索词和多条互补路径寻找候选。把标题命中、摘要线索和已核验全文分开，候选集交给研究者确认后再安排全文工作。
- 对公开、直接且授权清楚的 PDF，可以协助下载；需要登录、机构权限、验证码或授权不明的来源，给出合法地址、访问依据、建议文件名和 `research/inbox/authorized-pdfs/` 放置位置。
- 解析文本只是阅读辅助。核对原始 PDF 后，再把来源事实写成 `VERIFIED_SOURCE_FACT [identity @ locator]: claim`；不确定信息保留 `UNKNOWN`、`NOT_COMPARABLE` 或 `Chemical GAP`。
- 交接文档说明已覆盖的论点、仍缺的全文、不可比较处和推荐下一步。让研究者决定继续、暂停或进入 Synthesis。

## 轻量边界

Markdown 是工作记忆和交接，不需要数据库、内部 payload 或固定论文数量。能力不足时如实说明影响，可以降级为更窄的研究范围，但把代价展示给研究者。Research 的价值是让证据路线可读、可复核、可继续，而不是把协作锁在程序状态中。

凭据只来自研究者自己的环境或本地未跟踪配置，真实值不进入仓库、交接文档或缓存。原始来源、合法访问和人类核验拥有最终权威。
