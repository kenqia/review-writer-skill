# Review Writer — Chemical Review v2

这是 Chemical Review 的唯一开发源码仓。v2 收敛为四个可独立调用、可组合的 skills：

`chemical-review-intent → chemical-review-research → chemical-review-synthesis → chemical-review-qa`

它们通过显式 Markdown 交接，不证明科学有效性、不复现实验、不预测期刊接收，也不取代人类科学编辑。

## 源码与 plugin 边界

- **canonical source**：`.agents/skills/chemical-review-{intent,research,synthesis,qa}/`
- **发布 projection**：`plugins/chemical-review/skills/chemical-review-{intent,research,synthesis,qa}/`
- **plugin manifest**：`plugins/chemical-review/.codex-plugin/plugin.json`
- **同步命令**：`python scripts/build_plugin.py`
- **配置样例**：`.env.example`（真实凭据只能放在未跟踪的本地 env 文件）

发布 projection 由脚本生成。v1 orchestrator、payload 和七阶段 workflow 不在 v2 包边界内。

## 从 clone 开始

```bash
git clone https://github.com/kenqia/review-writer-skill.git
cd review-writer-skill
python scripts/build_plugin.py --check
python scripts/validate_plugin_package.py
python -B scripts/smoke_plugin.py
```

在 Codex 中添加本地 marketplace 后安装 `chemical-review@review-writer-skill`，再显式使用：

```text
$chemical-review-intent
$chemical-review-research
$chemical-review-synthesis
$chemical-review-qa
```

第一次可用主题：`ligand effects in nickel-mediated C–C coupling`。

## 四阶段交接

Intent 创建 `review-brief.md`；topic-only 草案含未决问题，只有显式确认后 Research 才能继续。已确认意图的变化先写 `review-brief.proposed.md`，确认后才生效。

Research 独占 `research/`：source registry、evidence notes、search log、comparability matrix、research gaps、download requests、`inbox/authorized-pdfs/` 和 handoff。真实运行先生成 `research/configuration-preflight.md`；缺少网络、推荐全文 provider 或 MinerU 时，必须明确选择配置后重跑、`accept_degraded` 或暂停，不会静默降级。它实现 OpenAlex、Semantic Scholar、Crossref、PubChem、ChEBI、Unpaywall、Europe PMC、CORE 和 MinerU 的可配置接口。全文候选按 `claim_relevance`（受影响的核心论点）进入队列；provider discovery 会从已确认 brief 的核心论点写入候选相关性并标明仍需 metadata/title screening，`priority` 与 `non_substitutability` 负责排序。没有核心论点关联的来源只记录为 gap，不按固定论文数截断队列。公开、直接且授权明确的 PDF 可自动下载；受限或授权不清的论文只生成合法下载地址和用户等待动作。Research 结果是 `READY_FOR_SYNTHESIS`、`WAITING_FOR_USER` 或 `RESEARCH_GAP`。

MinerU 是正式主解析器，`pdftotext` 是明确标注 `LOW_FIDELITY_FALLBACK` 的本地降级；原始 PDF 始终是来源权威，解析文本只是带 locator 的阅读辅助。凭据只能来自环境变量或未跟踪 env 文件，真实值不进入仓库、handoff 或 cache；provider 返回的 credential-bearing signed URL 也不会持久化，会显示 `WITHHELD_CREDENTIAL_BEARING_URL` 并要求重新获取不含凭据的合法 URL。

Synthesis 读取确认后的 Intent 和 Research 文档，写唯一内容源 `draft.md`，并从同一输入生成面向读者的 `reader-draft.md` 和带主张层级/locator 的 `research-draft.md`；三者不能各自独立演化。Research 只有在原始 PDF 核验后写入 `VERIFIED_SOURCE_FACT [identity @ locator]: claim`，Synthesis 才接受对应且内容一致的 `SOURCE_FACT`。正文还保留 `MODEL_SYNTHESIS`、`MODEL_HYPOTHESIS`、`UNKNOWN`、`NOT_COMPARABLE` 和 `Chemical GAP`；研究缺口下只允许明确标记的 unreviewed、evidence-bounded、partial-scope 候选稿。

QA 为同一版输入准备四个互不污染的干净上下文：evidence/locator、chemistry comparability/mechanism、synthesis novelty/rebuttal、overclaim/counterexample。arbiter 写 `qa/review-report.md`、`qa/qa-plan.md`、`qa/revision-plan.md`，保留冲突并把修改路由回 Intent、Research 或 Synthesis；不通过投票替人类接受科学结论。

## 验证

```bash
python -m unittest discover -s tests -p 'test_*.py'
python scripts/build_plugin.py --check
python scripts/validate_plugin_package.py
python scripts/package_plugin.py
```

工程绿灯不等于 Product Use、PUBLIC_E2E、HUMAN_ACCEPTANCE 或科学有效性；这些边界必须分开报告。
当前边界记录见 [`docs/v2-acceptance-report.md`](docs/v2-acceptance-report.md)。

## 许可证

本项目及 Chemical Review plugin 使用 MIT License。
