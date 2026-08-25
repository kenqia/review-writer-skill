# Chemical Review

Chemical Review 是一个轻量、可组合的化学文献综述 skill 包。它帮助研究者提出问题、整理证据、写出候选综述并收集反馈；Markdown 交接是产品本身，用户判断是科学决策的来源。

## 四个入口

- **Intent**：用一轮一轮的 grill 收敛 research question、core claims、scope、exclusions、audience、contribution 和 evidence expectations，最后由研究者确认 `review-brief.md`。
- **Research**：围绕 confirmed brief 发现候选、记录合法全文路线、整理 locator-bound evidence，并用一份自然语言 handoff 说明覆盖与缺口。
- **Synthesis**：先讨论写作计划，再以唯一的 `draft.md` 写出批判性综合；读者版和研究版是同一基线的视图。
- **QA**：用隔离的 fresh reviewer 角色检查证据、化学可比性、论证反驳和过度主张，再把反馈交回研究者。

每个入口只依赖自己的 `SKILL.md` 和 companion Markdown。没有中央 orchestrator、阶段 runner、隐藏 payload 或必须安装的 provider。

## 轻量协作规则

1. 先读当前阶段的 `SKILL.md`，再按它指向的 companion 文档选择需要的步骤；不要预先加载整个仓库。
2. 对研究者真正需要做的取舍给出推荐，但把决定留给研究者；可以用普通语言改写，不要求填写内部 schema。
3. 在 brief、Research handoff、写作计划和 QA 反馈之间使用短 Markdown 交接。只有会影响下游理解的内容才持久化。
4. 需要额外来源或项目材料时，先请求或读取明确 allowlist；不要自动加载全局 memory、历史项目、无关 parent context、凭据或 sibling checkout。
5. 文档可以提示人类确认，但不把流程变成不可解释的程序状态机。只有来源真实性、合法访问和明显的证据越界值得硬提醒。

## 研究者能看到的资产

- `review-brief.md`：当前已确认的研究意图。
- `research/`：候选、下载说明、证据笔记和研究 handoff；缺全文时记录合法 URL、访问依据、目标目录和下一动作。
- `draft.md`：Synthesis 的唯一正文基线。
- `reader-draft.md` / `research-draft.md`：同一正文的不同阅读视图。
- `qa/`：独立 reviewer 报告、冲突汇总和 revision routing。

这些文件是可读的工作材料，不是数据库。数字、机制和强结论要能回到来源 identity 与 locator；不确定时写 `UNKNOWN`、`NOT_COMPARABLE` 或 `Chemical GAP`。

## 领域语言

**SOURCE_FACT**：原始来源在明确 locator 处直接支持的事实。
**MODEL_SYNTHESIS**：模型跨来源比较、解释或归纳的判断。
**MODEL_HYPOTHESIS**：可由后续实验或文献检验的推断。
**NOT_COMPARABLE**：比较主轴字段不足以支持排序或强比较。
**Chemical GAP**：当前证据范围无法回答、需要新来源或人工核验的缺口。

比较时通常关注底物/材料、催化剂状态、配体、条件、终点、测量口径和机制证据；具体项目可以删减或增加字段，不把示例字段变成全局硬 schema。

## 可选 brief 专家审查

Intent 确认 brief 后可以把 role prompt、confirmed brief 和用户明确 allowlist 的材料交给一个 fresh sub-agent。它只返回 advisory findings，不读隐藏上下文、不调用 provider、不改文件；主会话展示建议，研究者决定是否写入 proposed brief 并确认。它不是同行评审、科学有效性认证或期刊接收预测。

## 产品边界

这是研究协作材料，不是自动投稿器、科学真值机或期刊接受预测器。`scripts/` 中的 Python 仅用于同步、打包和静态检查；它们不拥有阶段状态，也不是用户入口。真实 provider、API key、cookie 和 session 不写入仓库、Markdown 或发布包。
