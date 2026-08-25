# Chemical Review Grilling

把综述意图当作一棵小的 design tree，而不是一次性表单。每轮只问当前互不依赖、又会改变下游 Research 的少数问题；研究者回答后，再挑下一轮。可以回到前面的分支，但要说明哪些既有决定因此失效。

## 问题与答案来源

问题保持这个形状：

```text
❓ MODEL_QUESTION Q1 — 问题标题：为什么现在需要这个决定？
➡️ 推荐答案（MODEL_PROPOSAL）：基于当前材料，我建议……
✍️ USER_ANSWER：研究者接受、改写、拒绝，或明确写 UNKNOWN。
```

每个决定都保留来源：`MODEL_QUESTION` 是模型提出的待决问题，`USER_ANSWER` 只能来自研究者当前或明确 allowlist 的旧材料，`DEFAULT` 是研究者未回答时展示出来的可撤销工作假设，`UNKNOWN` 表示当前没有足够信息。推荐答案不是用户答案；模型不能把自己的推断写进 `USER_ANSWER`，也不能用 `DEFAULT` 冒充确认。

模型自己能查到的项目事实、代码事实和授权来源由模型查清后带回并标注来源；范围、排除项、比较方式、目标读者和贡献承诺留给研究者决定。涉及科学事实但没有明确来源时，保留 `UNKNOWN`，不要为了让树“收敛”而补写。

## 常见分支

先问：研究问题是否可回答、核心论点可能是什么、谁会使用这篇综述、它会改变什么判断、研究对象和时间边界在哪里。

再问：哪些对象纳入/排除、哪些字段足以比较、什么来源和 locator 才能支持强 claim、术语如何区分、`UNKNOWN` / `NOT_COMPARABLE` / `Chemical GAP` 怎么保留，以及什么样的覆盖程度足以建议开始 Research。不要在仍缺少研究问题或证据标准时讨论文风或 DOCX。

如果一个答案依赖另一个答案，留到下一轮；如果具体项目材料能解决它，先查 allowlist 内材料。每轮结束后给出一两句当前理解，让研究者纠正方向。frontier 只在已知分支都得到 `USER_ANSWER`、被明确保留为 `UNKNOWN`、采用可撤销 `DEFAULT` 并标出待确认，或被研究者排除时才算收敛；采用默认值本身不产生 confirmed brief。

## 收敛与返回

当研究者已经看过 research question、core-claim candidates、scope、exclusions、audience、contribution 和 evidence expectations，回显一份 shared understanding。研究者要明确说出确认（例如“确认这份 shared understanding”）；普通的“继续”“看起来可以”只有在上下文明确指向整份 brief 时才算确认，否则继续询问。确认前只继续对话，不写 confirmed brief、不启动 Research 或 advisory。

如果后续发现核心意图、范围、排除项或证据标准变了，先标出受影响的最早问题，重新提出该 frontier，并把旧答案保留在 revision snapshot 中。专家 advisory 只能检查已确认 brief，不能替研究者回答 design tree 问题。
