---
name: chemical-review-research
description: "Discover sources, route legal full text, parse authorized PDFs, and prepare locator-bound Research handoffs."
---

# Chemical Review Research

独立入口：读取已确认的 `review-brief.md`，独占项目 `research/`。输出 source registry、evidence notes、search log、comparability matrix、research gaps、download requests、authorized PDF inbox 和 `research-handoff.md`。

阶段结果只有：`READY_FOR_SYNTHESIS`、`WAITING_FOR_USER`、`RESEARCH_GAP`。受限或授权不清的全文只生成合法下载地址、访问依据、建议文件名、目标 `research/inbox/authorized-pdfs/`、受影响论点和下一动作；不绕过登录、机构权限、验证码或 paywall。用户放入 PDF 后重跑即可恢复。

正式 provider adapters：OpenAlex、Semantic Scholar、Crossref、PubChem、ChEBI、Unpaywall、Europe PMC、CORE。配置来自环境变量或未跟踪 env 文件；凭据不会进入 Markdown/cache。MinerU 是主解析器，`pdftotext` 是明确标注 `LOW_FIDELITY_FALLBACK` 的本地降级。

```bash
python research.py --project /path/to/project --fixture-dir /path/to/fixtures --env-file /path/to/local.env
```

原始 PDF 是来源权威，解析输出只可作为带 page/section locator 的阅读辅助。Research 不写 draft.md。
