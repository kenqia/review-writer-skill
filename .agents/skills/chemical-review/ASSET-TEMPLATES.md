# Chemical Review Asset Templates

这些模板是研究者可读的 Markdown 起点。实际项目可以增加内容，但不要删除它们承载的意图、领域和恢复信息。

## `review-intent.md`

```md
---
kind: review-intent
schema: 1
intent_revision: 0
confirmation: REQUIRED
journal_status: UNSET | PROPOSED | SELECTED | NOT_REQUIRED
journal_confirmation: REQUIRED | CONFIRMED | NOT_APPLICABLE
target_journal: <selected journal when any>
journal_guide_locator: <official guide locator when selected>
---

# Review Intent

## Research question
<!-- 当前综述要回答的化学问题；未知时写 open question。 -->

## Core-claim candidates
<!-- 模型和研究者考虑中的核心论点，不要求现在选定唯一答案。 -->

## Scope and exclusions
<!-- 包含什么、明确不包含什么、时间/体系/方法边界。 -->

## Audience or target journal
<!-- 目标读者或期刊；未确定时保留候选。 -->

## Journal candidates
<!-- 未指定期刊时由 agent 提出一到三个候选，研究者确认其一。 -->

## Expected contribution
<!-- 为什么现在需要这篇综述，它可能改变什么理解或研究决策。 -->

## Known facts
<!-- 从用户提供的 proposal、search log、PDF manifest 等项目材料中提取的已知信息；只保留与研究路线有关的内容。 -->

## Researcher context and prior knowledge
<!-- 只记录会改变检索路线、比较维度或证据解释的研究背景；不收集无关敏感个人信息。 -->

## Evidence standards and constraints
<!-- 原始论文、合法全文、页码/章节 locator、时间边界、访问和工具约束。 -->

## Frontier interview
<!-- 当前尚未解决、会改变研究路线的最小问题集合；每轮只推进当前 frontier。 -->

## Open questions
<!-- 需要 Grill 继续追问或由研究者决定的事项。 -->
```

## `domain-profile.md`

```md
---
kind: domain-profile
schema: 1
---

# Project Domain Profile

## Chemical subfield
<!-- 有机、无机、分析、物化、材料、药化或交叉领域。 -->

## Core systems
<!-- 分子、反应、材料、器件、分析对象或其他核心体系。 -->

## Canonical terms and synonyms
<!-- 当前项目采用的术语、同义词、缩写和避免混淆的词。 -->

## Boundary scenarios
<!-- 会改变范围或比较是否成立的边缘场景。 -->

## Evidence expectations
<!-- 本项目对原始论文、综述、标准、数据库和实验细节的适用要求。 -->

## Known capability limits
<!-- 当前模型、工具或来源的已知限制；不把限制伪装成事实。 -->
```

## `workflow-state.md`

```md
---
kind: chemical-review-workflow-state
schema: 1
phase: GRILL | RESEARCH | PROTOTYPE | PRD | ISSUES | IMPLEMENT | REVIEW
status: ACTIVE | WAITING_FOR_HUMAN | READY_FOR_NEXT_PHASE | CANDIDATE_READY
next_action: <one concrete action>
intent_revision: 0
intent_confirmation: NOT_REQUIRED | REQUIRED | CONFIRMED
execution_mode: continuous | acceptance
human_action: NONE | REQUIRED
journal_status: UNSET | PROPOSED | SELECTED | NOT_REQUIRED
journal_confirmation: REQUIRED | CONFIRMED | NOT_APPLICABLE
journal_guide_status: NONE | FETCHED
journal_guide_locator: <official guide locator>
journal_guide_digest: <sha256 of fetched guide content>
research_handoff: NONE | PROTOTYPE | PRD
research_handoff_rationale: <why this phase is proposed or blocked>
prototype_value_status: SUMMARY_ONLY | VALUE_PRODUCING
prototype_handoff: NONE | RESEARCH | PRD
prototype_handoff_rationale: <why this phase is proposed>
blueprint_status: NONE | ADAPTABLE
blueprint_revision: 0
unit_plan_status: NONE | READY_FOR_ACCEPTANCE | ACCEPTED
unit_ready: <comma-separated unit IDs or NONE>
content_revision: 0
package_status: INTEGRITY_HOLD | REVISION_REQUIRED | SUBMISSION_CANDIDATE
review_value_status: SUMMARY_ONLY | VALUE_PRODUCING
review_integrity_status: CLEAR | HARD_STOP
delivery_synchronization: SYNCHRONIZED
delivery_source_digest: <sha256 of the reviewed content revision>
feedback_revision: 0
feedback_category: NONE | INTENT | RESEARCH | PROTOTYPE | PRD | ISSUES | IMPLEMENT | REVIEW | DELIVERY
feedback_earliest_phase: NONE | GRILL | RESEARCH | PROTOTYPE | PRD | ISSUES | IMPLEMENT | REVIEW
feedback_requires_confirmation: NONE | REQUIRED
feedback_conflict: NONE | CONFLICT
feedback_next_action: <next action after the latest feedback>
updated: YYYY-MM-DD
---

# Workflow State

## Current goal

## Recently completed

## Open questions and risks

## Tool degradation or HUMAN_ACTION_REQUIRED

## Resume note
```

### `journal-guide.md`

```md
---
kind: journal-guide-snapshot
schema: 1
target_journal: <confirmed journal>
source_locator: <current official author-guide URL>
retrieved_at: YYYY-MM-DD
content_digest: <sha256 of guide content>
updated: YYYY-MM-DD
---

# Official Journal Guide Snapshot

## Target journal
## Source locator
## Guide content
```

### `review-feedback.md`

```md
---
kind: chemical-review-feedback-log
schema: 1
feedback_revision: 0
feedback_category: NONE | INTENT | RESEARCH | PROTOTYPE | PRD | ISSUES | IMPLEMENT | REVIEW | DELIVERY
feedback_earliest_phase: NONE | GRILL | RESEARCH | PROTOTYPE | PRD | ISSUES | IMPLEMENT | REVIEW
feedback_requires_confirmation: NONE | REQUIRED
feedback_conflict: NONE | CONFLICT
feedback_next_action: <next action after the latest feedback>
updated: YYYY-MM-DD
---

# Review Feedback Log

## Feedback 1
<!-- category、earliest phase、reason、conflict、base digest 和人类原话。后续反馈追加，不覆盖历史。 -->
```

### `human-edits/`

直接编辑的稿件按 `manuscript-edit-<feedback_revision>.md` 保存，带 `base_source_digest` 和 `conflict_status`。这是人类输入保留区，不是第二个正文权威；接受编辑前仍须通过 Implement 的中央合并边界。

## Research assets

Research adds two editable, project-local assets. They are working evidence
records, not a database or an authority over the original papers.

### `research-evidence.md`

```md
---
kind: research-evidence
schema: 1
intent_revision: 0
status: ACTIVE | WAITING_FOR_HUMAN | READY_FOR_NEXT_PHASE
human_action: NONE | REQUIRED
research_handoff: NONE | PROTOTYPE | PRD
readiness: DISCOVERY_READY | EVIDENCE_READY | CLAIM_READY
next_action: <one concrete action>
updated: YYYY-MM-DD
---

# Research Evidence Package

## Research question
## Project domain context
## Search paths
## Terms and chemistry entities
## Evidence notes
## Covered directions
## High-impact uncovered areas
## Major uncertainties
## Tool route
## Tool degradation or HUMAN_ACTION_REQUIRED
## Research handoff
## Coverage and stopping
<!-- 检索路径覆盖、连续无新增重要方向、边际收益和显式未覆盖区域；不使用固定论文数。 -->
## Preserved human edits and conflicts
## Human notes
```

### `source-registry.md`

```md
---
kind: research-source-registry
schema: 1
updated: YYYY-MM-DD
---

# Research Source Registry

<!-- 每条来源保留独立 identity、source kind、access basis、metadata/full-text/parser 状态、locator、digest、优先级和降级原因。用户 PDF 为 USER_AUTHORIZED；云解析必须有项目级明确授权。若使用 Readiness 列，必须显式写 DISCOVERY_READY/EVIDENCE_READY/CLAIM_READY。 -->
```

### `coverage-matrix.md`

```md
---
kind: research-coverage-matrix
schema: 1
updated: YYYY-MM-DD
---

# Research Coverage Matrix

<!-- 路径覆盖、query/request、new source、marginal gain、连续 no-new rounds 和 stopping reason。论文数量不是停止条件。 -->
```

### `run-budget.json` / `run-ledger.md`

`run-budget.json` 是机器可读 ledger；`run-ledger.md` 是其人类可读投影。至少记录 query、request、input/output token estimate、concurrency、retry、cache hit、parser pages/chunks、run id 和预算上限。冷启动从项目资产恢复，不重复传输未变化内容。

### `research-setup-wizard.md`

能力探测后生成的人类可执行配置清单。它只说明 adapter、权限、合法全文和恢复动作，不自动修改 shell、auth、environment 或 Codex 配置；拒绝配置时使用 no-key fallback。

### `literature-set.md`

```md
---
kind: layered-literature-set
schema: 1
intent_revision: 0
updated: YYYY-MM-DD
---

# Layered Literature Set

<!-- 新生成的条目带 [readiness: DISCOVERY_READY|EVIDENCE_READY]；没有该标记的旧项目条目按 DISCOVERY_READY 处理，不能支持 SOURCE_FACT，直到 Research 或人工核验补齐合法全文、locator 和显式 readiness。 -->

## Anchor/core
## Extension
## Background/definition
## Controversy
## Preserved human edits and conflicts
## Human notes
```

### `figure-inventory.md`

```md
---
kind: figure-inventory
schema: 1
updated: YYYY-MM-DD
---

# Figure/Scheme/Table Inventory

<!-- 每个图、反应 Scheme 和表格都保留 source_id、page/bbox 或 section locator、hash、resolution、extraction status、target section/paragraph、claim/citation IDs 和 transform history。只有 SOURCE + VERIFIED 资产可进入交付；ADAPTED/REDRAWN/GENERATED 必须显式保留状态并在交付前人工确认。 -->
```

## Prototype and PRD assets

### `prototype-result.md`

```md
---
kind: small-sample-review-prototype
schema: 1
prototype_revision: 0
selection_mode: PAPERS | SUBSECTION
value_status: SUMMARY_ONLY | VALUE_PRODUCING
prototype_handoff: RESEARCH | PRD
status: READY_FOR_NEXT_PHASE
updated: YYYY-MM-DD
---

# Small-sample Review Prototype

## Selection
## Representative rationale
## Prototype draft
## Value argument
## Comparisons
<!-- 每条 signal 记录 statement、所选 Evidence IDs 和 Value beyond summary。 -->
## Explanations
## Rebuttals
## New research questions
## Major risks
## Prototype decision
## Revision history
## Preserved human edits and conflicts
## Human notes
```

### `review-blueprint.md`

```md
---
kind: review-blueprint
schema: 1
blueprint_revision: 0
blueprint_status: ADAPTABLE
frozen: false
updated: YYYY-MM-DD
---

# Review Blueprint

## Research question
## Core-claim candidates
## Section structure
## Narrative line
## Comparison dimensions
## Evidence strategy
## Expected contribution
## Target-journal requirements
## Prototype basis
## Known risks
## Candidate research/writing units
## Revision history
## Human notes
```

## Issues and Implement assets

### `unit-plan.md`

```md
---
kind: research-writing-unit-plan
schema: 1
status: READY_FOR_ACCEPTANCE
blueprint_revision: 0
unit_count: 0
updated: YYYY-MM-DD
---

# Research/Writing Unit Plan

## Blueprint basis
## Units
## Initially parallel-ready
## Human notes
```

### `units/<unit-id>.md`

```md
---
kind: research-writing-unit
schema: 1
unit_id: <stable lowercase ID>
unit_kind: <term verification, comparison, mechanism branch, section claim, ...>
status: PENDING | READY | BLOCKED | COMPLETE | MERGED
prerequisites: <comma-separated IDs or NONE>
updated: YYYY-MM-DD
---

# Research/Writing Unit

## Purpose
## Prerequisites
## Completion signal
## Remaining uncertainty
## Latest result
<!-- findings、claim blocks、tool degradation 和 HUMAN_ACTION_REQUIRED -->
## Result history
## Preserved human edits and conflicts
## Human notes
```

### `merge-review.md`

```md
---
kind: central-unit-merge-review
schema: 1
status: CONFLICT | RESOLVED
updated: YYYY-MM-DD
---

# Central Unit Merge Review

## Selected units
## Conflicting sections
## Accepted resolutions
## Preserved human edits and conflicts
## Human notes
```

### `review-content.md`

```md
---
kind: single-review-content-source
schema: 1
content_revision: 0
status: ACTIVE
updated: YYYY-MM-DD
---

# Review Content Source

## Content blocks
<!-- section、claim level、contribution type、source units、evidence IDs、text -->
## Merge history
<!-- accepted unit IDs、deterministic merge key、blocks added；系统保存 history hash 用于安全恢复。 -->
## Preserved human edits and conflicts
## Human notes
```

## Review and delivery assets

Review 的四个输出必须在同一次运行中由同一个 `review-content.md` 修订生成。它们不是四份可独立演化的正文。

### `journal-profile.md`

```md
---
kind: journal-profile
schema: 1
status: NOT_SELECTED | SELECTED
target_journal: <journal or blank>
guide_locator: <official author-guide URL>
guide_digest: <sha256>
adaptation_status: MET | GAP | NOT_APPLICABLE
---

# Journal Profile

<!-- 只接受当前官方作者指南快照；指南变化或不可用时保留旧 profile，并把 recovery_action 写成 HUMAN_ACTION_REQUIRED。未指定期刊时保持 NOT_SELECTED，不猜测目标格式。 -->
```

### `generic-chemistry-draft.docx.manifest.md`

```md
---
kind: docx-export-manifest
schema: 1
profile_status: NOT_SELECTED | SELECTED
source_digest: <review-content.md sha256>
output_digest: <docx sha256>
---

# DOCX Export Manifest

<!-- DOCX 是 canonical review-content.md 的可重建 projection；manifest 记录 headings/references/figures/schemes/tables/equations、resolution 和 layout QA。digest 冲突时保留现有文件并暂停，不静默覆盖。 -->
```

### `clean-manuscript.md`

```md
---
kind: clean-review-manuscript
schema: 1
source_content_revision: 0
source_digest: <shared sha256>
delivery_status: INTEGRITY_HOLD | REVISION_REQUIRED | SUBMISSION_CANDIDATE
updated: YYYY-MM-DD
---

# <review title or research question>

<!-- 正常阅读和继续排版使用的干净正文；不包含内部 claim-level 标记。 -->
```

### `researcher-review.md`

```md
---
kind: researcher-review-view
schema: 1
source_content_revision: 0
source_digest: <shared sha256>
delivery_status: INTEGRITY_HOLD | REVISION_REQUIRED | SUBMISSION_CANDIDATE
updated: YYYY-MM-DD
---

# Researcher Review View: <review title or research question>

<!-- 只对关键内容块显示 claim level、contribution、Evidence IDs 和 source units。 -->
```

### `review-report.md`

```md
---
kind: multi-layer-review-report
schema: 1
package_status: INTEGRITY_HOLD | REVISION_REQUIRED | SUBMISSION_CANDIDATE
value_status: SUMMARY_ONLY | VALUE_PRODUCING
integrity_status: CLEAR | HARD_STOP
synchronization_status: SYNCHRONIZED
source_content_revision: 0
source_digest: <shared sha256>
updated: YYYY-MM-DD
---

# Multi-layer Review Report

## Review value
## Chemical reasoning
## Scientific integrity
## Intent alignment
## Journal adaptation
## Synchronization
## Non-blocking uncertainties
## Revision requests
## Tool degradation or HUMAN_ACTION_REQUIRED
## Human notes
```

### `submission-candidate-package.md`

```md
---
kind: submission-candidate-package
schema: 1
package_status: INTEGRITY_HOLD | REVISION_REQUIRED | SUBMISSION_CANDIDATE
source_content_revision: 0
source_digest: <shared sha256>
updated: YYYY-MM-DD
---

# Submission-candidate Package

## Candidate state
## Included assets
## Target-journal state
## Unresolved questions and next review inputs
## Tool degradation or HUMAN_ACTION_REQUIRED
## Boundary
<!-- 明示不声明科学有效性或期刊接收，最终权限属于人类科学编辑。 -->
```
