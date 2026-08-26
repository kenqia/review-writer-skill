# Intent Brief Contract

这份 companion 在 frontier 基本收敛后读取，用来把对话材料变成一份可审阅、可确认的 brief。它定义的是人类可读的契约，不是数据库 schema；字段可以按项目增删，但不能省略会改变 Research 路线的决定。

## 先整理来源，再写草案

从当前 Intent 材料和用户 allowlist 整理每个重要决定的来源：研究者的话标成 `USER_ANSWER`，模型提出的候选或解释标成 `MODEL_PROPOSAL`，未回答但暂时采用的假设标成 `DEFAULT`，没有足够依据的值标成 `UNKNOWN`。同一个字段同时有用户答案和模型建议时，用户答案优先；冲突不能静默合并。

不要把论文 metadata、摘要、snippet 或模型常识写成 confirmed brief 的科学事实。它们最多影响问题排序，不能替研究者承诺范围、贡献或证据标准。若研究者没有决定目标读者、期刊、时间边界或比较口径，写 `UNKNOWN` 并把它列为下一轮问题。

## Draft brief 的最低内容

以普通 Markdown 展示 draft，至少包括：

- research question：一句可回答的问题，以及它依赖的对象、时间或条件；
- core-claim candidates：准备检验的比较、机制、趋势或反驳，每条说明是候选而非已证实结论；
- scope 与 exclusions：纳入对象、明确排除对象、边界案例和 `Chemical GAP`；
- audience/target journal：读者、用途或目标期刊；未知就写 `UNKNOWN`；
- expected contribution：这篇综述希望改变什么判断，不能用“全面总结”掩盖具体贡献缺口；
- evidence expectations：来源层级、primary-study eligibility、原始 PDF/locator 要求、可比较字段、何时只能写 `NOT_COMPARABLE`，以及足以建议进入 Research 的覆盖标准。

每个仍有争议的项目都带上来源和待确认说明。不要为了填满段落发明数值、机制或期刊要求。

## 确认、提案与拒绝

展示 draft 后，暂停并请求研究者做 explicit confirmation of shared understanding。只有这次明确确认才可写入或更新 canonical `review-brief.md`，并在文件中记录确认轮次、研究者确认的范围和仍保留的 `UNKNOWN`。没有确认时，草案可以继续修改，但不得被 Research 当成 confirmed brief；可用 `WAITING_FOR_USER` 说明暂停原因。

confirmed brief 展示完毕后，主会话必须明确询问是否启动可选 brief advisory；这是独立的 opt-in checkpoint，不得由“继续”或默认值代替。Reviewer 只接收 role prompt、confirmed brief 和研究者明确 allowlist 的材料，且不得浏览、调用 provider、读取 hidden context 或编辑文件。结果按 actionable brief module 分组，每条 finding 都要有 severity、rationale、suggested change、confidence 和 unresolved questions；这些是建议，不是对来源或科学有效性的认证。

研究者可以 `skip`（不运行）、`accept selected`（选择或改写部分 finding）、`reject all` 或 `defer`。接受的建议形成标为 `UNCONFIRMED_PROPOSAL` 的 `review-brief.proposed.md`，逐条说明 finding/module、影响的字段、来源边界、研究者选择和未决问题。即使全部接受，也必须再次明确确认“将 proposal 合并到 confirmed brief”后才能更新 `review-brief.md`；第二次确认前不得静默覆盖 canonical brief。拒绝、暂缓或未确认 proposal 都保持旧 brief 不变。

Reviewer timeout、unavailable、malformed 或缺少必要材料时，报告 `ADVISORY_TIMEOUT`、`ADVISORY_UNAVAILABLE`、`ADVISORY_MALFORMED` 等具体原因和缺失部分，不能猜补、伪装成通过或生成 proposal，并保持 canonical brief 不变。是否重试或继续 Research 由研究者明确决定。

## 完成与恢复

这份契约完成的条件是：最低内容已展示，来源边界可读，研究者已明确确认，且下游需要的未知项没有被隐藏。仅有一个结构化文件、模型说“看起来完整”或 advisory 给出正面评价，都不算确认。确认后如果核心研究问题、scope、exclusions 或 evidence expectations 变化，必须回到受影响的 frontier，生成新的未确认提案并等待确认；旧的 confirmed brief 继续作为当前权威，直到新轮次被确认。
