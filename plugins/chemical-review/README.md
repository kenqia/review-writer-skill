# Chemical Review plugin

这是一个轻量的 Markdown-first skill 包：

`chemical-review-intent → chemical-review-research → chemical-review-synthesis → chemical-review-qa`

Intent 用 `grilling` 和 `domain-modeling` companion 逐轮收敛 brief，并可选地请 fresh sub-agent 做 advisory review。Research、Synthesis 和 QA 各自读取自己的三份 Markdown companion；它们通过可读的 brief、evidence、draft 和 feedback 交接，不依赖中央 orchestrator 或阶段代码。

Research 会把检索路线、全文授权和证据缺口讲清楚。需要配置或用户下载时，主会话停下来说明下一步；它不会因为某个 provider 不可用就暗中改写研究范围。原始来源和研究者核验拥有最终权威。

Synthesis 维护一个 `draft.md` 内容基线；QA 邀请独立 reviewer 视角并保留冲突。二者都支持普通语言反馈，研究者决定是否返工、接受或暂缓。

显式调用：

```text
$chemical-review-intent
$chemical-review-research
$chemical-review-synthesis
$chemical-review-qa
```

这个 plugin 是协作辅助，不是科学真值机、自动投稿器或期刊接收预测器。真实凭据只在研究者自己的环境中配置，不写入 plugin 或 Markdown handoff。
