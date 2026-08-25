---
name: chemical-review-synthesis
description: "Plan and write one evidence-bounded critical chemistry review draft from an accepted brief and Research handoff."
disable-model-invocation: true
---

# Chemical Review Synthesis

Synthesis 是一个自然语言写作工作台，只读已确认的 `review-brief.md`（confirmed brief）、研究者接受的 Research handoff、Research-owned evidence material 和用户明确 allowlist 的额外材料。不要主动读取无关 memory、历史、父上下文、凭据、cookie、session 或 sibling checkout；缺材料时报告缺口，不从隐藏上下文补写。

按顺序参考：

1. [`planning.md`](planning.md)：把证据、比较主轴和文章结构说清楚；
2. [`drafting.md`](drafting.md)：以 `draft.md` 为唯一内容基线，写出批判性叙述；
3. [`handoff.md`](handoff.md)：说明读者版、研究版、缺口和 QA 建议。

## 推荐节奏

先把写作计划交给研究者看一眼；只有明确确认 plan 后才开始 formal drafting。正文可以比较、解释、反驳并提出可检验假设，但每个强主张都应让读者看得出它来自来源事实、模型综合还是模型假设，并保留 locator、条件、对照、分母/测量口径和 limitation（适用时）。

同一份 `draft.md` 可以投影出干净的 `reader-draft.md` 和带依据提示的 `research-draft.md`。缺证据时降低语气，保留 `UNKNOWN`、`NOT_COMPARABLE` 和 `Chemical GAP`；研究范围不完整时明确写成 partial-scope candidate。

写作交接完成后，把 high-risk claims、counterexamples、open gaps 和 next action 交给研究者。只有研究者另行明确确认 draft 进入 QA，才调用 QA；这不是自动发布或科学接受按钮。

## 轻量边界

`draft.md` 是唯一 canonical 正文 baseline；`reader-draft.md` 和 `research-draft.md` 是同一 revision 的 projections，不是第二正文 authority。保持来源事实与推断可追溯即可，不要求内部 schema、固定章节数量或软件 payload。需要返工时保留旧稿、human edits 和反馈，用普通语言说明要回到 Research、Synthesis 还是仅做表达修订。Research 不完整时只能生成 `unreviewed; evidence-bounded; partial-scope` candidate，不得冒充完整综述。

完成 Synthesis 表示：计划已确认，canonical draft revision、views、边界、high-risk claims、counterexamples、gaps 和是否请求 QA 的 checkpoint 都可读；仅生成一份 prose 或 view 不等于完成。
