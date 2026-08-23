# Chemical Review Workflow Contract

## Single seam

`chemical-review` 是唯一的用户可见入口，即 **the single user-facing seam**。它接收主题或研究想法，读取当前 Markdown 状态，决定下一阶段，调用对应能力，并写回状态和研究资产。阶段内部可以调用其他 skill 或外部工具，但它们不成为第二个用户入口或第二个状态权威。

项目根目录由本次运行明确指定；三个资产直接保存在该目录。随 skill 提供的
`orchestrator.py` 是一个无数据库的最小文件编排器，用于验证启动、Grill 更新、冷启动恢复和确认边界；它不代替后续 Research 或写作能力。

## Inputs

最小输入是一个化学综述主题或研究想法。研究者可以随后补充目标读者/期刊、授权 PDF、已有文献、工具配置和自然语言反馈；缺少这些信息时，orchestrator 先追问或给出候选，不把空白静默当作确定答案。

## State contract

`workflow-state.md` 使用人类可读的 Markdown frontmatter 保存：

- `phase`：当前阶段；格式枚举以 [ASSET-TEMPLATES.md](ASSET-TEMPLATES.md) 为唯一来源，语义按本文件解释。
- `status`：`ACTIVE`、`WAITING_FOR_HUMAN`、`READY_FOR_NEXT_PHASE` 或 `CANDIDATE_READY`。
- `next_action`：下一次运行要做的一件可执行的事。
- `intent_revision`：综述意图的递增修订号。
- `intent_confirmation`：`NOT_REQUIRED`、`REQUIRED` 或 `CONFIRMED`。
- `human_action`：`NONE` 或 `REQUIRED`；对外报告 `HUMAN_ACTION_REQUIRED` 时设为 `REQUIRED`。
- `updated`：最近一次写入日期。

正文保留一小段人类可读摘要：当前目标、最近完成的工作、未决问题、工具降级影响和恢复提示。

## Phase transitions

1. 没有状态的主题进入 `GRILL`。
2. `GRILL` 只有在研究问题、范围、预期贡献和排除项足够明确，且没有未解决的核心意图决定时，才可建议进入 `RESEARCH`。
3. 首次综述必须经过 `RESEARCH`。后续循环可以依据 Research 交接判断或 Review 反馈继续 Research、进入 `PROTOTYPE` 或恢复到更早阶段。
4. Research 发现较高的问题边界、比较或价值风险时先进入 `PROTOTYPE`；风险较低且研究者接受 Research 的直接交接理由时可以进入 `PRD`。Prototype 若只有摘要复述或问题没有非平凡综合价值，回到 `GRILL` 或 `RESEARCH`。
5. `PRD` 形成蓝图后进入 `ISSUES`，`ISSUES` 形成有依赖关系的研究/写作单元后进入 `IMPLEMENT`。
6. `IMPLEMENT` 更新单一综述内容源后进入 `REVIEW`。
7. `REVIEW` 产生干净稿、研究者版和下一轮建议；反馈按最早失效阶段回退，不默认从头重做。
8. 缺少用户动作、授权来源或关键决定时使用 `WAITING_FOR_HUMAN`，并在 `next_action` 写出恢复动作；对外状态和交接报告使用 `HUMAN_ACTION_REQUIRED` 作为明确的用户动作标记。
9. 研究者确认候选包可以继续人工终审时使用 `CANDIDATE_READY`；这不是科学有效性或期刊接收状态。

## Research execution contract

Research 使用随入口提供的可替换 adapter seam。默认能力路线按“发现/元数据 → 化学实体/术语 → 合法全文 → PDF 解析”记录 OpenAlex、Semantic Scholar、Crossref、PubChem、ChEBI、Unpaywall/Europe PMC/CORE、MinerU/GROBID/Docling；配置文件或 adapter 名称只是能力选择，不是科学权威。具体公开职责和降级路线见 [docs/research/chemical-review-research-tools.md](../../../docs/research/chemical-review-research-tools.md)。

“默认路线”表示已配置 adapter 的首选次序，而不是内置凭据或假装外部服务已可用：发现依次优先 OpenAlex、Semantic Scholar、Crossref，术语优先 PubChem、ChEBI，全文优先 Unpaywall、Europe PMC、CORE，解析优先 MinerU、GROBID、Docling。某类能力没有可用 adapter 时必须记录降级，必要时请求用户完成最小配置。

一次 Research 运行必须完成以下可检查结果：

1. 生成七条可调整的检索路径（同义词、定义、方法/材料、关键事件、引用关系、作者/群体、最新进展），并保存查询语境。完成标准：`research-evidence.md` 的 `Search paths` 覆盖七条路径。
2. 将发现结果写入分层文献集，并保留可继续编辑的证据笔记。完成标准：`literature-set.md` 含 Anchor/core、Extension、Background/definition、Controversy 四个层级，且每条记录保留来源标识。
3. 记录工具路线、成功能力、替换路线和失败恢复动作；合法全文只接受 `OPEN_ACCESS`、`USER_AUTHORIZED` 或 `INSTITUTION_AUTHORIZED` 的明确访问依据与来源 locator，解析结果还必须含页码或章节 locator。完成标准：`Tool route` 和 `Tool degradation or HUMAN_ACTION_REQUIRED` 均有内容，或明确记录 `None recorded.`。
4. 给出 Research 交接判断，列出已覆盖方向、高影响未覆盖区域和主要不确定性；不以固定论文数量作为停止条件。完成标准：`Research handoff` 明确提议 `PROTOTYPE`/`PRD`，或说明为何仍 `WAITING_FOR_HUMAN`。

首选解析路线是 MinerU，GROBID 补充结构/参考文献，Docling 作为 fallback；解析器输出只能作为后续阅读线索，不能替代原始 PDF 或人工科学判断。

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
