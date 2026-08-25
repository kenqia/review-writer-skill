# Chemical Review Domain Modeling

这份 companion 只维护当前综述真正需要的化学语言。先看项目已有 `CONTEXT.md`；出现同一个词的两种含义时，直接指出差异，请研究者选一个 canonical term，再继续。

## 用场景澄清词义

优先用具体化学例子，而不是抽象定义：

- “ligand effect” 是 electronic、steric、coordination-state，还是其中一部分？
- “activity” 指 conversion、rate、TON 还是另一个终点？
- 两篇论文的 selectivity 底物、浓度、温度和终点不同，能排序还是只能记为 `NOT_COMPARABLE`？
- 论文作者的 mechanism 是直接观察到的证据，还是模型提出的 hypothesis？

用户确认一个词后，立即在根目录 `CONTEXT.md` 补一两句“它是什么”和可避免的混淆词。不要把 glossary 变成 brief、检索日志或实现笔记；没有新术语就不创建它。

## 只在值得时记录取舍

难以逆转、未来读者会疑惑、且确实比较过替代方案的决定，可以在 `docs/adr/NNNN-slug.md` 留三段短记录：

```md
# Short title

Context: 问题、约束和替代方案。
Decision: 选择了什么，以及不选什么。
Why: 这个取舍为什么值得保留。
```

普通措辞、一次性偏好和临时轮次决定留在对话或 `review-brief.md`。术语或关系仍不清楚时，标成 UNKNOWN，别替研究者发明领域语言。
