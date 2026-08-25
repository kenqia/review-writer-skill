---
name: chemical-review-intent
description: "A chemistry-adapted grill-with-docs interview that turns a review idea into a shared, evidence-bounded brief."
disable-model-invocation: true
---

# Chemical Review Intent

这是 Chemical Review 的轻量入口：用对话和几份 Markdown companion 把一个想法收敛成研究者愿意承担的 `review-brief.md`。先加载 [`grilling.md`](grilling.md)；遇到术语或关系需要澄清时，再加载 [`domain-modeling.md`](domain-modeling.md)。其中也包含 glossary 与 ADR 的短格式，需要写对应文件时再查。

## 一次自然的工作回合

1. 读取当前项目和用户明确点名的材料，找到已经知道的答案与仍然含混的决定。
2. 按 `grilling.md` 给出当前 frontier 的一小组问题；每题附一个推荐答案，等待研究者修改、接受或拒绝。
3. 术语被确认时，按 `domain-modeling.md` 更新项目语言；普通偏好留在对话中。
4. frontier 收敛后回显 shared understanding。研究者明确确认后，再写或更新 `review-brief.md`。

brief 只需要足够支撑下一步 Research：research question、core-claim candidates、scope、exclusions、audience/target journal、expected contribution、evidence standards 和 boundary scenarios。比较主轴、术语和停止规则在有帮助时补充；它们不是固定表单。

## 可选的 brief advisory

确认 brief 后，提醒研究者可选专家审查。研究者选择后再加载 [`expert-review.md`](expert-review.md)，把其中的 role prompt、confirmed brief 和明确 allowlist 的材料交给一个 fresh sub-agent。它只提供建议，最终修改仍由研究者确认。

## 轻量边界

保持一次只处理当前 frontier，保持事实和决定可区分，保持 brief 可读。没有新术语就不写 glossary，没有长期取舍就不写 ADR。完成 Intent 的标志是研究者确认了共享理解，而不是生成了某个内部文件数量。
