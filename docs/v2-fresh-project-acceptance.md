# Fresh-project document-boundary acceptance

这是一份可重复的人类验收 runbook，不是中央 runner、隐藏 payload 或第二套状态机。它验证五个核心 Markdown-first skill 及独立 Publication entrypoint 在一个全新项目目录中是否能依靠 documented artifacts 连续工作；执行者可以用真实可用工具，也可以使用受控的合法 PDF/capability fixtures。每次运行保留简短的输入 allowlist、观察、研究者决定和结果摘要，不把完整对话倾倒进仓库。

## Fixture 与边界

准备一个只包含以下内容的新项目：topic-only 用户消息、一个明确 allowlisted 的 chemistry note、一个受控 capability probe 结果和一份合法 fixture PDF。不要放入全局 memory、历史 transcript、凭据、cookie、session 或 sibling checkout。fixture PDF 的 stable identity、版本、页码 locator 和访问依据必须可人工复核。

每个 skill 从自己的 `SKILL.md` 开始，按 companion routing 渐进读取。阶段之间不举行额外 handoff 仪式；只把已持久化的 `review-brief.md`、stage result summary、Research evidence、Framework assets、`draft.md` 和 QA reports 作为下一步材料。

## 正常路径

1. **Intent**：从 topic-only 开始，提出 dependency-aware frontier questions，每题带推荐答案；至少一次回答保留 `USER_ANSWER`，一次未决定保留 `UNKNOWN`。展示 draft brief，等待 shared-understanding confirmation，确认后写 `review-brief.md` 和 Intent result summary。
2. **Optional advisory**：确认 brief 后明确询问 opt-in。分别运行 skip 与 opt-in fixture；opt-in reviewer 只收到 role prompt、confirmed brief 和 explicit allowlist，返回按模块分组的 finding。选择一条建议形成 `UNCONFIRMED_PROPOSAL`，在第二次确认前证明 canonical brief 不变，第二次确认后才生成新 revision snapshot。
3. **Research preflight**：只探测 brief 需要的 metadata、chemistry term、legal full-text 和 parser 路线。表格逐行有 pass/failure/not-verified 的实际证据、impact、official setup、配置位置/变量名和 rerun。选择 `configure_and_continue` 时观察到等待；重新预检后仍需单独确认 formal Research start。
4. **Discovery / acceptance**：从互补路径留下 raw hits、deduplicated stable identities、coverage、筛选理由和 INCLUDE/EXCLUDE/MAYBE 角色。至少保留一条 review/background/docking-only/generic-AI false positive。研究者接受当前候选集前，不创建全文队列；接受后只路由 accepted candidates。
5. **Full text / evidence**：对 fixture PDF 记录 access basis、binding、版本和 locator。对一个不可直接访问的候选写 legal download request，包含 claim、合法 URL、建议文件名、authorized inbox 和等待动作。parser probe 与 relevant-PDF per-run coverage 分开。解析摘录保持 `SOURCE_EXCERPT`；主 agent 对照原始 PDF 后才写 `VERIFIED_SOURCE_FACT`。
6. **Research result**：写 evidence ledger、progress 和 `research-handoff.md`，说明 path coverage、marginal gain、uncovered areas、预算/retry、Chemical GAP、不可比较和是否只能 partial-scope。研究者单独确认 handoff 是否可供 Framework 读取（若 brief 明确跳过 Framework，则记录该决定及其对完整性声明的影响）。
7. **Framework**：读取 confirmed brief、Research handoff/evidence ledger、可信 MinerU 文本和 explicit allowlist。生成 `evidence-matrix.md`、`case-cards.md`、`comparison-map.md`、`judgment-framework.md` 和 `framework-handoff.md`；覆盖兼容、冲突/负结果和无共同终点的场景。研究者确认 Framework 边界或明确 skip 后，才把适用结果交给 Synthesis；无共同终点时不得强行排名。
8. **Synthesis**：读取适用 Framework 资产、confirmed brief、Research-owned materials 和 explicit allowlist。先写 `synthesis-plan.md`，在 plan confirmation 前不开始 formal drafting。以唯一 `draft.md` 写一版批判性 synthesis；`reader-draft.md` / `research-draft.md` 只能是 projections。若 Research 或 Framework 不完整，稿件用普通语言标记 `unreviewed; evidence-bounded; partial-scope`。研究者另行确认 draft 进入 QA。
9. **QA**：默认启动四个 fresh reviewer，输入相同 revision 的 allowlisted brief/Research/Framework/draft/stage summary。检查 reviewer 不能互读或改稿；至少让一个 reviewer timeout/malformed，结果必须是该角度 `Incomplete QA`。arbiter 生成 `qa/review-report.md`、`qa/qa-plan.md`、`qa/revision-plan.md`，保留冲突和 locator 缺口。研究者用普通语言 accept/reject/defer，接受项路由到 earliest affected stage，QA 不自动改 draft 或推进 Delivery。
10. **Publication（独立入口）**：用户主动提供 `draft.md` 和 allowlist，生成 `journal-manuscript.md` 与 `journal-manuscript.docx`。验证内部流程元数据移除而科学限制、假设、partial scope、引用和视觉来源关系保留；DOCX 是 projection，不是第二正文权威。无目标期刊走中性路径；有 confirmed target journal（目标期刊）时必须先确认再读取 official guidance。

## 压力场景（pressure scenarios）

单独运行并记录观察：

- 只选择 configure-and-continue：不得 formal start、不得 discovery 或全文；
- provider/parser 失败：不得自动降级或自动换路线，除非研究者看到影响并明确接受；
- 未接受 candidate：不得进入全文；
- metadata/abstract/parser excerpt：不得升级为 primary 或 `VERIFIED_SOURCE_FACT`；
- 缺少 reviewer：不得报告完整 QA；
- projection/view 被修改：不得成为第二正文 authority，canonical `draft.md` 保持唯一基线；
- 核心 brief/scope/evidence standard 改变：保留旧 snapshot，回到 earliest affected stage；
- 独立重跑：只提供 confirmed brief、stage summary 和 allowlist，不提供上一轮聊天历史，仍能识别缺口并继续或请求材料。
- Framework 缺少共同终点：不得自动排名；必须保留 `NOT_COMPARABLE`、证据地图、研究类型学和局部解释链。
- Publication 清理：不得把模型假设变成来源事实，不得新增文献、删除限制或让 DOCX 成为第二正文权威。

## 结果分层

每次验收报告分别填写：

| 层级 | 观察内容 | 允许的结论 |
| --- | --- | --- |
| Document/package engineering | 文件边界、projection、Markdown-only、无 legacy runner/provider runtime | PASS/FAIL |
| Product Use | 新项目是否能按公开入口完成上述路径与恢复 | OBSERVED / NOT_OBSERVED |
| HUMAN_ACCEPTANCE | 研究者是否确认 brief、candidate、Research handoff、Framework 边界、plan、draft、QA routing | ACCEPTED / PENDING |
| Scientific validity | 原始来源、化学比较和结论是否科学成立 | 只能由研究者/专家另行判断 |
| Journal acceptance | 期刊是否接收 | 本产品不预测、不声明 |

绿色 package tests 或 fixture 通过不等于 Product Use、HUMAN_ACCEPTANCE、scientific validity 或 journal acceptance。运行结束后写一份短结果摘要，列出实际 allowlist、完成/未完成工作、证据边界、研究者决定、恢复点和下一步。
