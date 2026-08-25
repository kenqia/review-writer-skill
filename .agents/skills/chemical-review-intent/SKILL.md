---
name: chemical-review-intent
description: "A chemistry-adapted grill-with-docs interview that turns a review idea into a shared, evidence-bounded brief."
disable-model-invocation: true
---

# Chemical Review Intent

这是 Chemical Review 的轻量入口：用对话和语义 companion 把一个想法收敛成研究者愿意承担的 `review-brief.md`。Intent 只拥有意图材料；它不启动 Research、不调用 provider，也不主动读取无关 memory、历史、凭据、cookie、session 或 sibling checkout。

## 输入、输出与读取边界

- 默认只读用户当前消息、Intent 已有的 `review-brief.md`/提案/结果摘要，以及用户明确列入 allowlist 的项目材料。
- 先加载 [`grilling.md`](grilling.md)；需要化学术语或关系澄清时加载 [`domain-modeling.md`](domain-modeling.md)；要组织 brief 字段和确认语义时加载 [`brief-contract.md`](brief-contract.md)；要恢复、回顾或开启新一轮时加载 [`result-and-revision.md`](result-and-revision.md)。不要为了“完整”预先读取全部 companion。
- Intent 的 canonical artifact 是已确认的 `review-brief.md`。未确认材料只能是草案、提案或 advisory，不得被下游当成 confirmed brief。
- 本轮结束时留下人类可读的 Intent stage result summary；它供同会话继续、跨会话 resume 或独立入口使用，不是额外的仪式或隐藏状态。

## 一次自然的工作回合

1. 先检查 allowlist 内已有答案、旧 brief 和未解决决定；指出缺失信息，不用历史上下文猜补。
2. 按 [`grilling.md`](grilling.md) 给出当前 frontier 的一小组相互依赖最少的问题；每题附一个推荐答案，等待研究者接受、改写、拒绝或明确保留 `UNKNOWN`。
3. 研究者回答后，回显本轮更新和仍然影响下游的 frontier。只有当前分支已回答、明确 `UNKNOWN` 或被研究者排除，才进入 shared understanding。
4. 术语含义发生长期变化时，按 [`domain-modeling.md`](domain-modeling.md) 记录 canonical term；普通措辞和一次性偏好留在 brief 或对话中。
5. 按 [`brief-contract.md`](brief-contract.md) 展示可审阅的 draft brief。研究者作出明确 confirmation of shared understanding 后，才写入或更新 `review-brief.md`；确认前不得开始 Research 或 brief advisory。
6. 按 [`result-and-revision.md`](result-and-revision.md) 记录本轮结果、未决问题、必要快照和下一步确认。核心研究问题、范围或证据标准改变时，从受影响的最早 frontier 重新确认。

brief 至少说明 research question、core-claim candidates、scope、exclusions、audience/target journal、expected contribution 和 evidence expectations；比较主轴、术语、boundary scenarios、primary-study eligibility 与 coverage/stopping 在确实影响 Research 时补充。它不是固定表单，也不把模型建议伪装成用户决定。

## 可选的 brief advisory

确认 brief 后，提醒研究者可选专家审查。研究者选择后才加载 [`expert-review.md`](expert-review.md)，把其中的 role prompt、confirmed brief 和明确 allowlist 的材料交给一个 fresh sub-agent。它只返回 advisory findings，不读隐藏上下文、不浏览、不调用 provider、不改文件。主会话展示建议；研究者可以跳过、拒绝、暂缓或选择建议。被选择的建议先写入 `review-brief.proposed.md`，再次明确确认后才影响 canonical brief；超时、不可用或格式不完整都保持 `review-brief.md` 不变。

## 完成与非完成

Intent 完成表示：研究者看过 shared understanding 并明确确认了 brief，结果摘要说明了输入范围、已完成工作、可复用产物、边界、未决问题、决定和下一步。仅生成问题、草案、默认值、advisory 或某个文件，不等于确认完成；缺少关键回答时应停在 `WAITING_FOR_USER` 或 `UNKNOWN`，不能把草案交给 Research。
