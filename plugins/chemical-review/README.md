# Chemical Review plugin

这是一个轻量的 Markdown-first skill 包：

`chemical-review-intent → chemical-review-research → chemical-review-framework → chemical-review-synthesis → chemical-review-qa`

另有独立的 `chemical-review-publication` 交付入口，用于把已批准的 Markdown 草稿投影为期刊可读 Markdown 与 DOCX。

Intent 用 `grilling`、`brief-contract`、`domain-modeling` 和 `result-and-revision` companion 逐轮收敛 brief，保留答案来源、显式确认、结果摘要与 revision snapshot，并可选地请 fresh sub-agent 做 advisory review。Research 按语义边界读取 preflight、discovery、candidate acceptance、full-text/resume 和 evidence/handoff companion；Synthesis 和 QA 也各自按需渐进读取自己的 Markdown companion。它们通过可读的 brief、evidence、draft 和 feedback 交接，不依赖中央 orchestrator 或阶段代码。

Research 会把检索路线、全文授权和证据缺口讲清楚。需要配置或用户下载时，主会话停下来说明下一步；它不会因为某个 provider 不可用就暗中改写研究范围。原始来源和研究者核验拥有最终权威。

Synthesis 维护一个 `draft.md` 内容基线；QA 邀请独立 reviewer 视角并保留冲突。二者都支持普通语言反馈，研究者决定是否返工、接受或暂缓。

显式调用：

```text
$chemical-review-intent
$chemical-review-research
$chemical-review-framework
$chemical-review-synthesis
$chemical-review-qa
$chemical-review-publication
```

这个 plugin 是协作辅助，不是科学真值机、自动投稿器或期刊接收预测器。真实凭据只在研究者自己的环境中配置，不写入 plugin 或 Markdown handoff。
