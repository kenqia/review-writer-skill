# Fresh-project acceptance result — 2026-08-25

这是对 [fresh-project document-boundary runbook](v2-fresh-project-acceptance.md) 的一次受控本地 fixture run，记录于 2026-08-25。它主要记录当日的 Intent、Research、Synthesis 和 QA 基线；Framework/Publication 扩展后的补充 seam 结果见 [`framework-publication-acceptance-result-20260826.md`](framework-publication-acceptance-result-20260826.md)。这不是一次真实化学综述，也没有调用外部 provider、登录服务或真实凭据。

## Run setup

- Fresh project fixture：临时隔离目录，初始输入只有 topic-only 消息、`allowlist/chemistry-note.md`、一份受控 capability 结果和一份人工构造的公开 fixture PDF；运行后已将可复现材料提交到 [`tests/fixtures/v2-fresh-project/`](../tests/fixtures/v2-fresh-project/)。
- PDF check：`file` 识别为 PDF 1.4；`pdfinfo` 报告 1 page、未加密、版本 1.4。
- 历史基线（2026-08-25）Public entrypoints read：Intent、Research、Synthesis、QA 四个 `SKILL.md`，随后按 companion routing 只读取当前阶段所需文档；这不是当前五核心入口的完整声明。
- Durable fixture artifacts：当前 committed bundle 包含 35 个 Markdown/PDF 文件，包括 confirmed brief、Intent result summary、advisory skip/opt-in/reject/defer/timeout/malformed 分支、`UNCONFIRMED_PROPOSAL`、二次确认后的 revision snapshot、preflight pass/failure/not-verified、candidate acceptance/return、ambiguous binding、progress、download request、evidence ledger、Research handoff、synthesis plan、canonical draft、两个 projections 和四个 reviewer reports/QA materials。
- Context scan：fixture 中没有 token、API key、cookie、session、signed URL、hidden context 或 sibling checkout material。

## Observed path

| Slice | Observed result | Evidence in fixture |
| --- | --- | --- |
| Intent topic-only → confirmed brief | PASS | `review-brief.md`、`intent-result.md`；target journal 保留 `UNKNOWN`，确认来源明确 |
| Optional advisory skip | PASS | `intent-result.md` 记录明确 skip；canonical brief 未被 advisory 改写 |
| Optional advisory opt-in/proposal | PASS | `intent/advisory-findings.md`、`review-brief.proposed.md` 和 before/after snapshots；BF-001 selected，二次确认前 canonical 不变，确认后 revision 2 保留旧 snapshot |
| Optional advisory reject/defer/failure branches | PASS | committed fixture includes reject-all, defer, timeout and malformed outputs; each keeps canonical brief unchanged |
| Preflight and configuration wait | PASS | `research/preflight.md` 逐行记录 pass/not-verified、影响、setup、rerun；`configure_and_continue` 分支停在等待，之后另行确认 formal start |
| Discovery and candidate acceptance | PASS | `search-log.md`、`candidates.md`、`candidate-acceptance.md`；F-002 review-only 被排除，F-003 docking-only 保持 MAYBE，只有 F-001 被接受 |
| Research failure/return/binding branches | PASS | preflight failure, return-to-discovery and ambiguous PDF binding are held with explicit reason and no promotion |
| Legal full text and binding | PASS | `download-requests.md` 给出 claim、合法 URL、建议文件名、authorized inbox 和 next action；fixture PDF 绑定到稳定 identity |
| Excerpt versus verified fact | PASS | `evidence-ledger.md` 同时保留 `SOURCE_EXCERPT` 与直接核验后的 `VERIFIED_SOURCE_FACT`，机制保留 `UNKNOWN` |
| Coverage/stopping/resume | PASS | `progress.md`、Research handoff 记录 path coverage、marginal gain、uncovered areas、budget/retry、Chemical GAP 和恢复点 |
| Synthesis plan and draft | PASS | `synthesis-plan.md` 先确认；`draft.md` 标记 `unreviewed; evidence-bounded; partial-scope`，views 作为 projections |
| QA isolation and incomplete handling | PASS | 四份角色报告分开且包含 claim/paragraph、locator、severity、rationale、confidence、earliest stage、suggested action；`review-report.md` 明确一个 malformed/timeout 角度为 `Incomplete QA`；冲突保留 |

## Pressure observations

- 选择 `configure_and_continue` 的分支没有 formal start、discovery、全文或解析授权；配置完成后仍需要单独确认。
- 未接受的 F-003 没有进入全文 routing；review-only/docking-only 记录没有膨胀成 primary evidence。
- parser excerpt 没有直接作为 source fact；只有 fixture PDF 与 locator 核验后才出现 `VERIFIED_SOURCE_FACT`。
- `draft.md` 是唯一 canonical baseline；`reader-draft.md` 和 `research-draft.md` 被记录为 projections，QA 没有改写 draft 或推进 Delivery。
- 缺失/错误 reviewer 被报告为 `Incomplete QA`，没有被剩余角色冒充完整 QA。
- 以 confirmed brief、stage summaries 和 allowlist 重新读取时，路径能识别已知缺口；没有上一轮聊天历史也没有自动补上下文。
- advisory opt-in 分支只把 role prompt、confirmed brief 和 allowlisted note 交给 reviewer；selected finding 先进入 `UNCONFIRMED_PROPOSAL`，二次确认前没有 canonical mutation，确认后旧 brief snapshot 仍可恢复。

## Layered result

| Layer | Result | Boundary |
| --- | --- | --- |
| Document/package engineering | OBSERVED PASS | 17 tests、projection check、package validation、bundled/install smoke、Ruff 全部通过 |
| Product Use | OBSERVED — controlled fixture only | 历史基线的四个公开 Markdown entrypoint 正常路径、暂停、恢复和压力材料在本地 fixture 中可追踪；Framework/Publication 补充结果见 2026-08-26 报告 |
| HUMAN_ACCEPTANCE | PENDING | 本次是 agent-run fixture；真实研究者仍需确认 brief、候选、原始 PDF、handoff、plan、draft 和 QA finding |
| Scientific validity | NOT_ASSERTED | fixture 不证明化学结论、证据穷尽性或比较成立 |
| Journal acceptance | NOT_CLAIMED | 本产品不预测期刊接收 |

该结果把 #59 从“只有 runbook/静态 marker”提升为一次有记录、可复现 fixture bundle 的受控 document-boundary observation；it does not replace 真实研究者 Product Use、HUMAN_ACCEPTANCE 或科学审查。
