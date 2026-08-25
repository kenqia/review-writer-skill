# Chemical Review Grilling

把综述意图当作一棵小的 design tree，而不是一张一次性表单。每轮只问眼下互不依赖、又会影响后续研究的几个问题；研究者回答后，再挑下一轮。可以随时回到前面的分支。

问题保持这个形状：

```text
❓ Q1 — 问题标题：为什么现在需要这个决定？
➡️ 推荐答案：基于当前材料，我建议……
```

推荐答案是工作假设，研究者可以接受、改写或拒绝。模型自己能查到的项目事实、代码事实和授权来源由模型查清后带回；范围、排除项、比较方式、目标读者和贡献承诺留给研究者决定。

## 常见分支

先问：研究问题是否可回答、核心论点可能是什么、谁会使用这篇综述、它会改变什么判断、研究对象和时间边界在哪里。

再问：哪些对象纳入/排除、哪些字段足以比较、什么来源和 locator 才能支持强 claim、术语如何区分、UNKNOWN / NOT_COMPARABLE / Chemical GAP 怎么保留，以及什么样的覆盖程度足以开始 Research。

如果一个答案依赖另一个答案，留到下一轮；如果具体论文或项目材料能解决它，先查材料。每轮结束后给出一两句当前理解，让研究者纠正方向。frontier 只在已知分支都得到回答、被明确保留为 UNKNOWN 或被研究者排除时才算收敛。

## 收敛

当研究者已经看过 research question、核心论点、scope、exclusions、audience、contribution 和 evidence expectations，回显一份 shared understanding。研究者明确确认后再写 `review-brief.md`，把仍未决定的地方标成 UNKNOWN 或待讨论；确认前只继续对话，不启动 Research 或 advisory。

如果后续发现核心意图变了，修改 brief 前重新问受影响的分支。完整 brief 后才提醒可选的 advisory sub-agent；专家审查不能替研究者回答设计树问题。
