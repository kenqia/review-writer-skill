---
name: chemical-review-research
description: "Discover sources, route legal full text, parse authorized PDFs, and prepare locator-bound Research handoffs."
---

# Chemical Review Research

独立入口：读取已确认的 `review-brief.md`，独占项目 `research/`。当前运行的唯一可变事实源是 `research/manifest.json`；source registry、provider status、terms-and-entities、evidence notes、evidence-matrix、search log、comparability matrix、research gaps、download requests、authorized PDF inbox 和 `research-handoff.md` 都是从该 manifest 投影的交接资产。

阶段结果只有：`READY_FOR_SYNTHESIS`、`WAITING_FOR_USER`、`RESEARCH_GAP`。受限或授权不清的全文只生成合法下载地址、访问依据、建议文件名、目标 `research/inbox/authorized-pdfs/`、受影响论点和下一动作；不绕过登录、机构权限、验证码或 paywall。用户放入 PDF 后重跑即可恢复。

真实 Research 在发现、全文定位或解析前会先生成 `research/configuration-preflight.md`。硬门槛只有确认 brief、至少一个实际可达/可用结果的 discovery route 和当前项目可探针的 parser route；Unpaywall、CORE、PubChem、ChEBI、Europe PMC 缺失只记录为 optional degradation，不阻塞 `configure_and_continue`。能力记录区分 `CONFIGURED`、`REACHABLE` 和 `USABLE_RESULTS`，不以 doctor 报告或字段存在替代真实 provider 验证。这不增加阶段结果枚举；选择降级后仍使用下方三种既有结果。

调用方首次运行不得替用户选择：读取预检文件和 CLI 的 `CONFIGURATION_CHOICE_REQUIRED` 输出，向用户展示缺失能力、影响和恢复方式，等待用户明确选择；`configure_and_continue` 只记录等待配置，用户完成配置后重跑，`accept_degraded` 才允许继续执行。

Discovery 先记录 raw hits、provider/query coverage 和 DOI/title/version 去重后的 unique candidates；随后逐条执行 title、abstract、publication type、year 和 topic relevance screening，写入 `INCLUDE` / `EXCLUDE` / `MAYBE`、理由、置信度和 primary/secondary/background/excluded evidence role。只有 included 或 review-relevant maybe 才能进入全文路线。全文下载候选必须带有 `claim_relevance`（受影响的核心论点）；自动 provider discovery 会从已确认 brief 的核心论点写入候选相关性。可选的 `priority` 和 `non_substitutability` 用于排序。没有核心论点关联的来源只记录为 `RESEARCH_GAP`，不进入用户下载队列。队列按当前候选集自然形成，不用固定论文数截断。

每个已解析相关来源都会在 manifest 的四层 Evidence Matrix 中写入 Research kernel、Chemistry comparison spine、brief/domain-derived modules 和 review-specific evidence plan。自动解析只能产生 `SOURCE_EXCERPT`/`EXCERPT`；原始 PDF 核对后才可由人工提升为 `VERIFIED_SOURCE_FACT`/`VERIFIED`。缺失字段保留 `UNKNOWN`、`NOT_COMPARABLE` 或 `Chemical GAP`。

正式 provider adapters：OpenAlex、Semantic Scholar、Crossref、PubChem、ChEBI、Unpaywall、Europe PMC、CORE。配置来自环境变量或未跟踪 env 文件；凭据不会进入 Markdown/cache。Research 会从 frontmatter/行内 `Topic:` 提取主题，将核心论点拆成有限的短检索词；不会把整句研究问题发送给 metadata 或化学实体 provider。MinerU 是主解析器，命令适配器首选传递 `--input-dir` 并读取批处理 Markdown，同时兼容显式的单 PDF wrapper；`pdftotext` 是明确标注 `LOW_FIDELITY_FALLBACK` 的本地降级。

MinerU 只有在配置预检找到项目内已授权 PDF 并完成一次真实解析探针后才标记为 `READY`；没有可探针 PDF 时标记为 `NOT_VERIFIED`，解析失败时标记为 `FAILED`，不得仅凭 `MINERU_COMMAND` 字段存在宣称可用。

provider 返回的 signed URL 如果含有 `api_key`、`access_token`、签名、userinfo 或 Bearer 参数，不会写入 registry、handoff 或 download request；Research 会写明 `WITHHELD_CREDENTIAL_BEARING_URL`，保留真实降级并要求重新获取不含凭据的合法 landing/download URL。

```bash
python research.py --project /path/to/project --env-file /path/to/local.env
# after reviewing configuration-preflight.md and choosing a route:
python research.py --project /path/to/project --env-file /path/to/local.env --config-choice accept_degraded
```

原始 PDF 是来源权威，解析输出只可作为带 page/section locator 的阅读辅助。只有 Agent/研究者核对原始 PDF 后，才能在 `evidence-notes.md` 写入 `VERIFIED_SOURCE_FACT [identity @ locator]: claim`；自动解析生成的 `SOURCE_EXCERPT` 或未标记的 `SOURCE_FACT` 不能直接成为正文事实。Research 不写 draft.md。
