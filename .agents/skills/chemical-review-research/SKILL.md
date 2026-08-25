---
name: chemical-review-research
description: "Discover sources, route legal full text, and prepare a human-readable chemistry evidence handoff."
disable-model-invocation: true
---

# Chemical Review Research

Research 是一个文档型证据工作台，只在 Intent 已产生并由研究者确认的 `review-brief.md` 上工作。它拥有候选、检索、全文请求、证据 ledger 和 Research 结果摘要；不把任何 provider、parser 或脚本当成核心依赖，也不静默改写 `review-brief.md`。

默认只读当前 confirmed brief、Research 自己的阶段材料、上一次 Research result summary，以及研究者明确列入 allowlist 的额外材料。不要主动加载无关 memory、隐藏历史、父上下文、凭据、cookie、session 或 sibling checkout。若 brief 或必要摘要缺失，说明缺口并请求材料，不能从上一段聊天猜补。

按语义边界渐进加载本目录 companion：

1. [`preflight.md`](preflight.md)：快速了解当前网络、检索、全文和解析能力；
2. [`discovery-and-screening.md`](discovery-and-screening.md)：围绕 brief 找候选、去重、解释取舍；
3. [`candidate-acceptance.md`](candidate-acceptance.md)：在全文成本扩大前，把候选集交给研究者接受、返回或暂停；
4. [`full-text-and-resume.md`](full-text-and-resume.md)：路由合法全文、绑定授权 PDF、区分解析摘录与核验事实，并保留可恢复的进度；
5. [`evidence-and-handoff.md`](evidence-and-handoff.md)：维护 evidence ledger、coverage/stopping 和可读 Research handoff。

## 推荐节奏

- 先按 [`preflight.md`](preflight.md) 对当前 brief 所需的最佳路线和有现实价值的备选路线做小型实际探针。每条路线必须报告 pass、failure 或 not-verified 的证据、影响、官方配置入口、配置位置/变量名和 rerun 动作。`configure_and_continue` 只表示去配置后回来，不表示正式 Research 开始；必须另行得到 `confirm_formal_start` 或清楚的自然语言确认。
- 按 [`discovery-and-screening.md`](discovery-and-screening.md) 用同义词、定义、方法/材料、关键事件、引用、作者和近期进展等互补路径寻找候选；保存 raw hits、去重关系、稳定 identity、路径覆盖和筛选理由。
- 按 [`candidate-acceptance.md`](candidate-acceptance.md) 在全文成本扩大前展示候选角色、覆盖、误收风险和高影响缺口。研究者接受或明确修改后，才可进入全文路线；不能自动接受或自动降级。
- 按 [`full-text-and-resume.md`](full-text-and-resume.md) 路由公开且授权清楚的 PDF；登录、机构权限、验证码或授权不明时写合法下载请求。解析文本只是阅读辅助；核对原始 PDF、identity 与 locator 后，才把来源事实写成 `VERIFIED_SOURCE_FACT`。
- 按 [`evidence-and-handoff.md`](evidence-and-handoff.md) 记录版本、访问依据、locator、证据等级、比较字段、UNKNOWN、NOT_COMPARABLE、Chemical GAP、coverage/stopping 与 Research result summary。让研究者决定继续、暂停、补证据或进入 Synthesis。

## 高影响 checkpoint 与完成契约

正式 Research start、候选集 acceptance 和 Research handoff 进入 Synthesis 都是高影响 checkpoint。普通检索、去重、比较和解析可以连续推进；checkpoint 必须把影响说清楚并等待研究者决定。能力失败时不能静默降级；只有研究者明确接受 evidence-bounded 的窄范围后，才能按降级范围继续。

Research 的完成表示：当前输入范围、已走路线、可复用证据、证据边界、未覆盖区域、未解决问题、研究者决定和下一步都写入 readable Markdown。只生成候选、预检表、parser 输出或某个文件，不等于 formal Research 完成；缺配置、候选未接受、全文不可得或 locator 未核验时，应报告 `WAITING_FOR_USER`、`RESEARCH_GAP` 或 `NOT_VERIFIED`。

Markdown 是工作记忆和交接，不需要数据库、内部 payload 或固定论文数量。Research 的价值是让证据路线可读、可复核、可继续，而不是把协作锁在程序状态中。

凭据只来自研究者自己的环境或本地未跟踪配置，真实值不进入仓库、交接文档或缓存。原始来源、合法访问和人类核验拥有最终权威。
