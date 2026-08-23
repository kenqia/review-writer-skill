# Chemical Review Workflow Contract

## Single seam

`chemical-review` 是唯一的用户可见入口，即 **the single user-facing seam**。它接收主题或研究想法，读取当前 Markdown 状态，决定下一阶段，调用对应能力，并写回状态和研究资产。阶段内部可以调用其他 skill 或外部工具，但它们不成为第二个用户入口或第二个状态权威。

项目根目录由本次运行明确指定；三个资产直接保存在该目录。随 skill 提供的
`orchestrator.py` 是一个无数据库的最小文件编排器，用于验证启动、Grill 更新、冷启动恢复和确认边界；它不代替后续 Research 或写作能力。

## Inputs

最小输入是一个化学综述主题或研究想法。研究者可以随后补充目标读者/期刊、授权 PDF、已有文献、工具配置和自然语言反馈；缺少目标读者和期刊时，orchestrator 提议一到三个期刊候选，研究者确认后才读取其当前官方作者指南，不把空白静默当作确定答案。

## State contract

`workflow-state.md` 使用人类可读的 Markdown frontmatter 保存：

- `phase`：当前阶段；格式枚举以 [ASSET-TEMPLATES.md](ASSET-TEMPLATES.md) 为唯一来源，语义按本文件解释。
- `status`：`ACTIVE`、`WAITING_FOR_HUMAN`、`READY_FOR_NEXT_PHASE` 或 `CANDIDATE_READY`。
- `next_action`：下一次运行要做的一件可执行的事。
- `intent_revision`：综述意图的递增修订号。
- `intent_confirmation`：`NOT_REQUIRED`、`REQUIRED` 或 `CONFIRMED`。
- `human_action`：`NONE` 或 `REQUIRED`；对外报告 `HUMAN_ACTION_REQUIRED` 时设为 `REQUIRED`。
- `journal_status`：`UNSET`、`PROPOSED`、`SELECTED` 或 `NOT_REQUIRED`。
- `journal_confirmation`：`REQUIRED`、`CONFIRMED` 或 `NOT_APPLICABLE`。
- `journal_guide_status`：选定期刊后的 `FETCHED` 标记；其 locator 和 digest 也写入状态。
- `updated`：最近一次写入日期。

正文保留一小段人类可读摘要：当前目标、最近完成的工作、未决问题、工具降级影响和恢复提示。

## Phase transitions

1. 没有状态的主题进入 `GRILL`。
2. `GRILL` 只有在研究问题、范围、预期贡献和排除项足够明确，且目标读者已给出，或目标期刊候选已被确认并读取当前官方指南时，才可建议进入 `RESEARCH`。
3. 首次综述必须经过 `RESEARCH`。后续循环可以依据 Research 交接判断或 Review 反馈继续 Research、进入 `PROTOTYPE` 或恢复到更早阶段。
4. Research 发现较高的问题边界、比较或价值风险时先进入 `PROTOTYPE`；风险较低且研究者接受 Research 的直接交接理由时可以进入 `PRD`。Prototype 若只有摘要复述或问题没有非平凡综合价值，回到 `GRILL` 或 `RESEARCH`。
5. `PRD` 形成蓝图后进入 `ISSUES`，`ISSUES` 形成有依赖关系的研究/写作单元后进入 `IMPLEMENT`。
6. `IMPLEMENT` 更新单一综述内容源后进入 `REVIEW`。
7. `REVIEW` 产生干净稿、研究者版和下一轮建议；反馈按最早失效阶段回退，不默认从头重做。
8. 缺少用户动作、授权来源或关键决定时使用 `WAITING_FOR_HUMAN`，并在 `next_action` 写出恢复动作；对外状态和交接报告使用 `HUMAN_ACTION_REQUIRED` 作为明确的用户动作标记。
9. 研究者确认候选包可以继续人工终审时使用 `CANDIDATE_READY`；这不是科学有效性或期刊接收状态。

## Human-feedback iteration contract

反馈是自然语言协作输入，不要求研究者填写内部 Review 表单。`record_feedback()` 接收普通评论，也可以接收直接编辑后的正文；orchestrator 把它记录到 `review-feedback.md`，并依据反馈内容选择最早失效阶段：意图→Grill、来源/定义→Research、综合价值→Prototype、结构→PRD、单元依赖→Issues、内容合并→Implement、审查或交付→Review。

- 核心研究问题、范围、排除项、受众或目标期刊的反馈先写入 `Pending intent feedback`，原意图保持权威；只有 `confirm_feedback(accept=True)` 后才递增 `intent_revision` 并允许下游重跑。拒绝则移除待定反馈，不改写原意图。
- 直接人工稿件保存在 `human-edits/manuscript-edit-<revision>.md`，保留原文和来源 digest。digest 不匹配时状态为 `WAITING_FOR_HUMAN`/`CONFLICT`；orchestrator 不会静默覆盖或自动择一。
- 每次反馈追加一条带 revision、分类、最早阶段、冲突状态和下一动作的 Markdown 记录。冷启动从该日志和 `workflow-state.md` 恢复；Research、blueprint、unit 结果和单一内容源不会因反馈路由被删除。
- `resume_cycle()` 默认只把状态移到路由阶段；当反馈影响 Review/交付且提供新的 Review assessment 时，它会把旧双轨输出移入 `review-history/feedback-<revision>/`，再从现有单一内容源重新生成同步视图。该操作不重跑上游 Research/Prototype/PRD/Issues。
- 反馈未能明确匹配时保留到 Review，不能因为无法分类而丢失。每轮结束仍返回当前候选状态、未解决问题、工具降级/HUMAN_ACTION_REQUIRED 和下一动作。

## Research execution contract

Research 使用随入口提供的可替换 adapter seam。默认能力路线按“发现/元数据 → 化学实体/术语 → 合法全文 → PDF 解析”记录 OpenAlex、Semantic Scholar、Crossref、PubChem、ChEBI、Unpaywall/Europe PMC/CORE、MinerU/GROBID/Docling；配置文件或 adapter 名称只是能力选择，不是科学权威。具体公开职责和降级路线见 [docs/research/chemical-review-research-tools.md](../../../docs/research/chemical-review-research-tools.md)。

“默认路线”表示已配置 adapter 的首选次序，而不是内置凭据或假装外部服务已可用：发现依次优先 OpenAlex、Semantic Scholar、Crossref，术语优先 PubChem、ChEBI，全文优先 Unpaywall、Europe PMC、CORE，解析优先 MinerU、GROBID、Docling。某类能力没有可用 adapter 时必须记录降级，必要时请求用户完成最小配置。

一次 Research 运行必须完成以下可检查结果：

1. 生成七条可调整的检索路径（同义词、定义、方法/材料、关键事件、引用关系、作者/群体、最新进展），并保存查询语境。完成标准：`research-evidence.md` 的 `Search paths` 覆盖七条路径。
2. 将发现结果写入分层文献集，并保留可继续编辑的证据笔记。完成标准：`literature-set.md` 含 Anchor/core、Extension、Background/definition、Controversy 四个层级，且每条记录保留来源标识。
3. 记录工具路线、成功能力、替换路线和失败恢复动作；合法全文只接受 `OPEN_ACCESS`、`USER_AUTHORIZED` 或 `INSTITUTION_AUTHORIZED` 的明确访问依据与来源 locator，解析结果还必须含页码或章节 locator。完成标准：`Tool route` 和 `Tool degradation or HUMAN_ACTION_REQUIRED` 均有内容，或明确记录 `None recorded.`。
4. 给出 Research 交接判断，列出已覆盖方向、高影响未覆盖区域和主要不确定性；不以固定论文数量作为停止条件。完成标准：`Research handoff` 明确提议 `PROTOTYPE`/`PRD`，或说明为何仍 `WAITING_FOR_HUMAN`。

首选解析路线是 MinerU，GROBID 补充结构/参考文献，Docling 作为 fallback；解析器输出只能作为后续阅读线索，不能替代原始 PDF 或人工科学判断。

## Prototype and PRD execution contract

Prototype 是化学综述的小样本试作，不是软件原型或语言质量评分。agent 从分层文献集选少量代表性论文，或提出一个小节并绑定该小节使用的 Research evidence IDs，主动尝试比较、解释、反驳和提出新问题；`PrototypeSubmission` 只是 agent 内部交接 seam，不要求研究者填写表单。

1. 说明选择了哪些论文或小节，以及它们为何能暴露当前问题的价值与风险。完成标准：`prototype-result.md` 同时记录 `Selection` 和 `Representative rationale`；论文选择与小节绑定的 evidence IDs 都能在 `literature-set.md` 找到。
2. 分开记录比较、解释、反驳和新研究问题，并说明这些分析相对摘要复述增加了什么研究价值；允许其中部分为空，不使用总分或字数替代判断。每个 `PrototypeSignal` 必须绑定所选 evidence IDs，comparison 至少跨两个 evidence records。完成标准：四个对应章节和 `Value argument` 都存在，至少一条 evidence-bound signal 有非空 statement 与 `Value beyond summary`，并有整体价值论证时才可标记 `VALUE_PRODUCING`；否则标记 `SUMMARY_ONLY`。这只是可供研究者审阅的交接证据，不证明模型综合在科学上正确。
3. 报告主要风险并提出 Research 或 PRD 交接；研究者可以接受，也可以换样本继续探索。完成标准：状态保存 `prototype_handoff` 和理由，Research 资产不被 Prototype 重写。

PRD 把已保存的意图、Research 与可选 Prototype 结果转成 `review-blueprint.md`。蓝图必须包含研究问题、核心论点候选、章节结构、叙事主线、比较维度、证据策略、预期贡献、期刊要求、风险和候选研究/写作单元。它保持 `ADAPTABLE` 与 `frozen: false`：新证据只修订受影响部分，并在 `Revision history` 保留原因和旧内容；不预先分配每句话或冻结论文清单。Prototype 重跑若发现 tracked section 被直接编辑，会把编辑原文保存在 `Preserved human edits and conflicts`；蓝图修订覆盖同一章节前，会在 revision history 明示并保留检测到的人类编辑。

## Issues and Implement execution contract

Issues 把研究者接受的蓝图拆成少量 `ResearchWritingUnit`。每个 unit 必须说明 purpose、prerequisites、completion signal 和 remaining uncertainty；unit 类型保持开放，可以是术语核验、检索/解析、跨论文比较、机制分支、争议解释或章节论点。依赖图必须无环；ready 查询和结果提交都会重新核验 prerequisites，手改或陈旧的 `READY` 状态不能绕过未完成 blocker。多个 ready units 可以由 agent 并行执行或以任意安全顺序提交结果，不要求本 skill 自建线程池、任务队列或后台服务。

Implement 遵守两个写入边界：

1. 每个 worker 只写 `unit-plan.md` 已声明的 `units/<unit-id>.md`，保存 findings、completion evidence、remaining uncertainty、tool degradation/HUMAN_ACTION_REQUIRED 和可选 claim blocks。完成标准：rogue unit 或依赖未满足的 unit 不能提交；受阻 unit 保留当前结果并可在能力恢复后 retry。
2. claim block 区分 `SOURCE_FACT`、`MODEL_SYNTHESIS`、`MODEL_HYPOTHESIS`，并标明 comparison、explanation、rebuttal、trend、hypothesis 或 section draft 等贡献类型。所有已声明 evidence IDs 都必须存在于当前 `literature-set.md`，且 `SOURCE_FACT` 不能省略 evidence IDs；模型综合与假设仍保留其性质，不被伪装成文献事实。
3. unit worker 不能直接修改 `review-content.md`。orchestrator 通过显式 central merge 接受结果；同一 section 的兼容贡献可以并存，只有 agent 判断为真实语义冲突的 section 才进入 `merge-review.md` 等待 resolution。每次成功 merge 在 hash-bound history 保存 accepted unit IDs 与确定性 merge key；若内容已写而 unit 状态写入失败，以同一集合或其中已记录的失败子集重试只完成状态收敛，不重复追加内容。直接编辑 Merge history 会被保留并进入 `HUMAN_ACTION_REQUIRED`，不能被当成恢复事实。完成标准：所有候选结果和冲突输入都保留，人类编辑被检测并作为下一次合并输入，不发生静默覆盖。

`review-content.md` 是双轨交付的单一内容源；Implement 只生成带 claim-level 语义的内容块，Review 再从同一次内容修订生成干净稿和研究者版。工程测试只验证依赖、资产和合并契约，不证明化学判断正确。

## Review and synchronized delivery contract

Review 接受 agent 对化学推理、意图对齐、修订请求、普通不确定性和科学诚信问题的判断，以及从目标期刊当前官方指南整理的适配要求。它不把字符串扫描或固定总分冒充科学审稿，也不要求研究者填写内部 JSON。

1. `review-content.md` 是唯一正文来源；同一次运行从同一 `content_revision` 和 `source_digest` 生成 `clean-manuscript.md` 与 `researcher-review.md`。完成标准：两个视图的正文主张一致并携带相同 digest；已有 Review 输出不会被静默覆盖。
2. 干净稿不显示内部 claim-status 标记。研究者版只对关键内容块显示 `SOURCE_FACT`、`MODEL_SYNTHESIS` 或 `MODEL_HYPOTHESIS`，并保留 contribution、evidence IDs 和 source units；不要求逐句贴标签。
3. 多层 Review 分别检查综合价值、化学推理、科学诚信、意图对齐、目标期刊适配和双视图同步。Review agent 必须显式给出 `VALUE_PRODUCING` 或 `SUMMARY_ONLY` 及其理由；comparison、explanation、rebuttal、trend、hypothesis 和 new research question 等 contribution 标签只是审查语境，不能自动证明正文超越摘要复述。`SUMMARY_ONLY` 触发可执行修订，不代表模型观点必然正确或错误。
4. 默认 hard stop 只限四类：`FABRICATED_OR_UNFINDABLE_SOURCE`、`MISQUOTED_SOURCE_DATA`、`INVENTED_CHEMICAL_FACT`、`INFERENCE_AS_SOURCE_FACT`。每个 hard stop 必须给出正文与来源 locator；普通分歧、证据空白和不确定性记录为 `NON_BLOCKING` 提示。
5. 目标期刊要求必须保留当前官方作者指南快照、来源 locator 和内容 digest，并按 `MET`、`GAP` 或 `NOT_APPLICABLE` 记录。没有特定期刊但已确认目标读者时，期刊适配为 `NOT_APPLICABLE`。期刊 gap 可使候选包进入 `REVISION_REQUIRED`，但任何状态都不是接收预测。
6. Review 同时生成 `review-report.md` 与 `submission-candidate-package.md`。候选包生成前必须验证 Research、PRD、unit-plan、unit 资产和单一内容源均存在且 frontmatter kind 正确；候选包状态只允许 `INTEGRITY_HOLD`、`REVISION_REQUIRED` 或 `SUBMISSION_CANDIDATE`；即使是 `SUBMISSION_CANDIDATE`，也只表示可交给人类科学编辑继续核验，不声明科学有效性或期刊接收。

## Intent confirmation

当模型建议改变研究问题、核心论点方向、范围、排除项、目标读者或目标期刊时，the change requires **explicit confirmation**：

1. 保留原意图和 `intent_revision`；
2. 以自然语言说明变更、理由、受影响资产和替代选项；
3. 将 `intent_confirmation` 设为 `REQUIRED`；
4. 在研究者明确接受前，不重写下游蓝图、单元或正文。

研究者确认后才递增 `intent_revision`，设为 `CONFIRMED`，并从最早受影响的阶段继续。

## Ownership and recovery

- orchestrator 负责写入 `workflow-state.md`、`review-intent.md`、`domain-profile.md`，并负责跨单元合并。
- 人类可以直接修改这些 Markdown；下一次运行必须把差异作为人类输入，不能静默抹平。
- 每个并行单元先写自己的研究资产或变更建议；只有 orchestrator 能把已接受的结果并入单一综述内容源。
- 工具失败、解析不完整、来源受限和等待用户动作都必须保留在状态摘要中，以便冷启动恢复。
- 不创建数据库、隐藏状态服务、Web 看板或另一份“真相”。
