---
name: chemical-review-qa
description: "Use independent chemistry review roles to surface evidence, comparability, argument, and overclaim risks."
---

# Chemical Review QA

QA 是一个轻量的第二双眼睛。读取研究者愿意审查的 brief、Research evidence、`draft.md` 和 Synthesis handoff，再按需要加载：

1. [`reviewers.md`](reviewers.md)：四个 fresh reviewer 的角色和输入边界；
2. [`arbiter.md`](arbiter.md)：如何把独立观察和真实冲突汇总成一份可读报告；
3. [`revision-routing.md`](revision-routing.md)：如何用普通语言决定下一步。

## 推荐节奏

主会话可以分别请四个 fresh sub-agent 看证据定位、化学可比性、综合与反驳、过度主张与反例。每个 reviewer 只看明确 allowlist 的同一版材料，并返回观察和建议；不需要共享其它 reviewer 的上下文。

arbiter 保留分歧、缺失信息和 locator，把它们整理成 `qa/` 下的报告与 revision plan。研究者逐条接受、拒绝或暂缓，随后决定回到 Intent、Research、Synthesis 或只做交付表达。

QA 反馈是协作材料，不是投票结果。研究者可以直接说“这条比较不可比”“补看该 PDF 第 3 页”或“保留这个假设”，主会话把它翻译成下一步工作。
