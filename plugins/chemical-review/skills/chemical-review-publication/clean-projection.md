# Publication-clean Markdown projection

本页说明如何把研究版 Markdown 变成普通期刊读者能读的稿件。目标是隐藏流程噪声，而不是隐藏科学限制。

## 先保护 canonical draft

把输入 draft 的 revision、语言和 allowlist 写在工作摘要中。`journal-manuscript.md` 是从该 revision 重新构建的 projection；不要直接覆盖 `draft.md`，不要把 Publication 的修辞改动当成对 Research ledger、Framework matrix 或 QA report 的确认。

如果输入仍是 `unreviewed`、`evidence-bounded` 或 `partial-scope`，这些事实要转为 ordinary scientific language（读者能理解的自然语言），例如“本综述覆盖了……，尚未评估……”。不能因为删除标签而删除 evidence boundary（证据边界）。

## 内部标签的自然语言转换

可以移除以下流程元数据：MinerU/parser 状态、附件或 PDF 数量、Evidence ID、QA routing、stage/unit 状态、内部 resume 标签和仅供 agent 定位的短码。若标签承载科学含义，则将含义改写为正文：

| 内部含义 | 期刊稿中的处理 |
| --- | --- |
| `SOURCE_FACT` / `VERIFIED_SOURCE_FACT` | 写成带适当引用和 locator 支持的来源事实；不必保留标签文字。 |
| `MODEL_SYNTHESIS` | 用“综合这些研究可见……”等普通语言，并说明比较条件。 |
| `MODEL_HYPOTHESIS` | 用“提示”“可能”“有待检验”等明确的假设语气，不能写成已证实机制。 |
| `UNKNOWN` | 写明当前研究未报告、尚无法确定或数据不足。 |
| `NOT_COMPARABLE` | 说明终点、条件、对照或测量口径不同，不能直接排序或合并。 |
| `Chemical GAP` | 写成仍需新来源、统一测量、原始核验或实验验证的具体缺口。 |
| `SOURCE_EXCERPT` | 删除内部标签，但仅在其内容确实由来源支持且 citation/locator 保留时写入正文；解析摘录不能自动升级为事实。 |

不要把 source identity、作者解释、跨研究综合和模型假设揉成同一种语气。引用、脚注或参考文献可以保留必要的来源关系，但不把 agent 的内部 payload 暴露给读者。

## 可做与不可做的编辑

可以：重写摘要和结论、调整标题层级、合并重复段落、按比较主轴组织章节、整理表格/图题/参考文献、修正显然的语言错误，并把 limitations（限制）改成 ordinary scientific language。

不可以：新增文献或实验结果；补齐没有来源的数值、分母或条件；do not delete 反例、适用边界、冲突或 Chemical GAP；do not change core judgment；把作者 hypothesis 或 `MODEL_HYPOTHESIS`（model hypothesis）伪装成 `SOURCE_FACT`；用更强的动词掩盖不确定性。这里的 no new literature、no unsupported claims 是硬边界。

每次重要改写都应能回答“它在 draft 的哪一段、由哪一来源或 Framework 资产支持、是否改变了语气或范围”。无法回答时，保留原文并把问题交回科学修订。

## 期刊读者检查

在交付前通读 `journal-manuscript.md`：读者不应需要知道 MinerU、附件数量、QA 路由或 Evidence ID 才能理解论点；但读者应能看到研究对象、条件、比较口径、限制、冲突、证据强弱和假设边界。检查引用与参考文献是否一致，表格/图题是否有来源，partial-scope 是否诚实，语言是否仍为输入语言。
