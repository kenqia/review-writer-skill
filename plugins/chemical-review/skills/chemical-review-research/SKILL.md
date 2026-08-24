---
name: chemical-review-research
description: "Discover sources, route legal full text, parse authorized PDFs, and prepare locator-bound Research handoffs."
---

# Chemical Review Research

独立入口：读取已确认的 `review-brief.md`，独占项目 `research/`。输出 source registry、provider status、terms-and-entities、evidence notes、search log、comparability matrix、research gaps、download requests、authorized PDF inbox 和 `research-handoff.md`。

阶段结果只有：`READY_FOR_SYNTHESIS`、`WAITING_FOR_USER`、`RESEARCH_GAP`。受限或授权不清的全文只生成合法下载地址、访问依据、建议文件名、目标 `research/inbox/authorized-pdfs/`、受影响论点和下一动作；不绕过登录、机构权限、验证码或 paywall。用户放入 PDF 后重跑即可恢复。

真实 Research 在发现、全文定位或解析前会先生成 `research/configuration-preflight.md`。缺少网络路由、推荐全文 provider 或 MinerU 时不会默认静默降级，必须明确选择：`configure_and_continue`（配置后重跑）、`accept_degraded`（接受记录在案的降级）或 `pause`（暂停）。这不增加阶段结果枚举；选择降级后仍使用下方三种既有结果。

全文下载候选必须带有 `claim_relevance`（受影响的核心论点）；自动 provider discovery 会从已确认 brief 的核心论点写入“候选相关性”，并明确仍需 metadata/title screening。可选的 `priority` 和 `non_substitutability` 用于排序。没有核心论点关联的来源只记录为 `RESEARCH_GAP`，不进入用户下载队列。队列按当前候选集自然形成，不用固定论文数截断。

正式 provider adapters：OpenAlex、Semantic Scholar、Crossref、PubChem、ChEBI、Unpaywall、Europe PMC、CORE。配置来自环境变量或未跟踪 env 文件；凭据不会进入 Markdown/cache。MinerU 是主解析器，`pdftotext` 是明确标注 `LOW_FIDELITY_FALLBACK` 的本地降级。

provider 返回的 signed URL 如果含有 `api_key`、`access_token`、签名、userinfo 或 Bearer 参数，不会写入 registry、handoff 或 download request；Research 会写明 `WITHHELD_CREDENTIAL_BEARING_URL`，保留真实降级并要求重新获取不含凭据的合法 landing/download URL。

```bash
python research.py --project /path/to/project --env-file /path/to/local.env
# after reviewing configuration-preflight.md and choosing a route:
python research.py --project /path/to/project --env-file /path/to/local.env --config-choice accept_degraded
```

原始 PDF 是来源权威，解析输出只可作为带 page/section locator 的阅读辅助。只有 Agent/研究者核对原始 PDF 后，才能在 `evidence-notes.md` 写入 `VERIFIED_SOURCE_FACT [identity @ locator]: claim`；自动解析生成的 `SOURCE_EXCERPT` 或未标记的 `SOURCE_FACT` 不能直接成为正文事实。Research 不写 draft.md。
