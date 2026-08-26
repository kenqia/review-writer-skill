# Research Candidate Acceptance

这份 companion 在 discovery/screening 产生一组可读候选后读取。候选集接受是全文成本扩大前的高影响 checkpoint（high-impact checkpoint），不是自动筛选结果，也不是永久冻结文献范围。

## 展示什么

给研究者一份当前候选集摘要，至少能看到：

- 每条候选的 stable identity、标题/年份、关联 core claim、`INCLUDE`/`EXCLUDE`/`MAYBE` 和具体理由；
- 暂定 evidence role（primary、secondary、background 或 excluded）及为什么不是更强的角色；
- 每条 discovery path 的覆盖、raw hit→deduplicated identity 关系、可能的 false positives、误收风险和高影响未覆盖方向；
- 哪些候选已经有合法全文路线，哪些仍需 Research 后续获取，哪些因 identity、化学对象或证据标准而 `UNKNOWN`；
- 如果需要继续 discovery，建议补充的 query、路径或边界，而不是一个固定论文数量目标。

## 研究者决定

研究者可以用普通语言：接受当前集合、只接受其中一部分、退回补检索，或暂停。也可以使用 `accept_candidates`、`return_to_discovery` 和 `pause` 作为清晰标签，但标签不是必须记住的命令。

- 接受：只把明确接受且与本轮 brief 相关的候选交给 full-text routing；保留被排除和待确认条目及理由。
- 修改：研究者改变角色、纳入/排除边界或 core claim 时，先更新候选记录，再重新展示 coverage 和风险；不能静默把修改传给全文阶段。
- 退回：从受影响的 discovery path 继续，并保留旧集合和本次反馈；新发现可以增量加入，不需要从零重做。
- 暂停：写 `WAITING_FOR_USER`，不创建正式全文队列。

没有明确 acceptance 时，候选不得进入全文下载、解析或 evidence ledger 的 VERIFIED_SOURCE_FACT 路线；only accepted candidates may enter full-text routing。配置缺失、预检失败或用户只选择 `configure_and_continue` 也不构成 candidate acceptance；不能自动选择次优路线或自动缩小范围。

## 完成与恢复

本页完成表示：研究者的接受/返回/暂停决定、适用范围、coverage、false-positive 风险和高影响缺口都已写入 `research/candidate-acceptance.md`（或项目指定的等价 Markdown）。它不声称候选事实已被全文核验，也不声称研究已经穷尽。

若后续出现新 query、合法全文、identity 冲突或 brief 修订，保留当前 acceptance 记录，新增一轮增量决定；不要覆盖研究者原话或把 `MAYBE` 提升为 `INCLUDE` 而不说明原因。
