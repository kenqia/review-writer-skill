---
name: chemical-review
description: "Use when a researcher wants to plan, research, draft, review, or iteratively improve a critical narrative chemical literature review from a topic or research idea."
---

# Chemical Review

这是一个以研究者为主导、以模型为研究同伴的化学文献综述工作流。它使用一个唯一的 orchestrator seam，维护少量 Markdown 研究资产，并把 Review 反馈路由回最早失效阶段。

## Start or resume

1. 读取 [WORKFLOW.md](WORKFLOW.md)（阶段、状态、Research/Prototype/PRD/Review 行为和确认语义）与 [ASSET-TEMPLATES.md](ASSET-TEMPLATES.md)（意图、领域、工作流和阶段资产的字段及人类可读结构）；当本次运行要启动、恢复或校验资产时才读取它们。完成标准：两份参考文件均已读完，且当前运行采用的阶段词和字段来自同一份模板。
2. 在用户明确的项目根目录检查 `workflow-state.md`、`review-intent.md` 和 `domain-profile.md`；可执行的最小文件编排器见 [orchestrator.py](orchestrator.py)。完成标准：三个资产全部存在且 frontmatter 可读，或已确认这是没有状态的全新项目。
3. 全新项目只向用户索取主题或研究想法，然后由 orchestrator 创建三个资产并进入 Grill；不要求用户填写内部表单或 JSON。完成标准：`workflow-state.md` 的 `phase` 为 `GRILL`，并且意图资产含有未猜测的开放问题和下一步提示。
4. 已有状态时读取 `workflow-state.md` 的 `phase`、`next_action` 和 `intent_confirmation`，从保存阶段继续，不重启 Grill 或补写缺失历史。完成标准：对外返回的阶段和下一动作与刚加载的 Markdown 状态一致。
5. 本次阶段工作完成后更新下一动作、未决风险和恢复提示；Research 维护证据资产，Prototype 维护小样本结果，PRD 维护可修订蓝图，Issues/Implement 维护独立 unit 资产并只通过 orchestrator 合并单一内容源，Review 从该内容源同步生成双轨稿件和诚实候选包，反馈回路维护 `review-feedback.md` 与 `human-edits/`。完成标准：重新加载三个核心资产和已存在的阶段资产能重建本次运行的阶段、修订号、ready units、Review 状态、反馈路由和人类动作要求。

## Phase loop

| Phase | 这一阶段必须解决的问题 |
| --- | --- |
| Grill | 研究问题、范围、价值假设、目标读者/期刊和排除项是否清楚？ |
| Research | 哪些术语、论文、事件、争议和证据线索值得继续研究？ |
| Prototype | 少量代表性材料能否产生非平凡的比较、解释或新问题？ |
| PRD | 综述蓝图、章节主线、比较维度和后续研究/写作单元是什么？ |
| Issues | 哪些研究/写作单元可执行，哪些单元被什么前置条件阻塞？ |
| Implement | 如何把研究、比较、推理和写作结果合并到单一内容源？ |
| Review | 价值、化学推理、诚信底线、意图对齐和交付格式是否需要下一轮？ |

Research、Prototype、PRD、Issues、Implement、Review 和反馈迭代的执行契约见 [WORKFLOW.md](WORKFLOW.md)。Review 生成干净正文、带主张层级的研究者版、多层审查报告和投稿候选包；反馈可以自然语言、直接编辑或评论进入，并只回退到最早失效阶段。本入口只暴露一个统一路由、状态恢复、确认和中央合并边界。

## Human boundary

- 研究者是人类科学编辑，拥有最终科学叙事和交付文本的接受、修改或拒绝权。
- 模型可以挑战用户、提出综合判断和假设；核心研究问题、范围、排除项、目标读者或期刊发生变化时，必须先提出变更并等待明确确认。
- 目标读者可以直接确认；目标期刊未指定时，orchestrator 只提出一到三个候选，研究者确认后读取当前官方指南并保留快照、locator 与 digest，不能静默选择期刊。
- 需要用户配置 API、提供授权 PDF 或解决受限来源时，输出 `HUMAN_ACTION_REQUIRED`，说明缺失能力、影响阶段、最小动作、降级路线和恢复方式。
- 人类的直接编辑和自然语言意见都是下一轮输入；不得静默覆盖它们。

## State discipline

- `workflow-state.md` 是当前阶段和下一动作的唯一状态投影。
- `review-intent.md` 和 `domain-profile.md` 是当前项目的意图与领域语境基线。
- orchestrator 是唯一的用户入口和跨阶段合并者；并行研究/写作单元不能直接互相覆盖综述正文。
- Markdown 状态是可读的工作记录，不是数据库、隐藏知识库或第二权威。
- 不自动宣称科学结论正确或期刊接收；最终交付是可继续人工核验的投稿候选包。
