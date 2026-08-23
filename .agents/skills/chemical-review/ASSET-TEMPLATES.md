# Chemical Review Asset Templates

这些模板是研究者可读的 Markdown 起点。实际项目可以增加内容，但不要删除它们承载的意图、领域和恢复信息。

## `review-intent.md`

```md
---
kind: review-intent
schema: 1
intent_revision: 0
confirmation: REQUIRED
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

## Expected contribution
<!-- 为什么现在需要这篇综述，它可能改变什么理解或研究决策。 -->

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
human_action: NONE | REQUIRED
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
updated: YYYY-MM-DD
---

# Workflow State

## Current goal

## Recently completed

## Open questions and risks

## Tool degradation or HUMAN_ACTION_REQUIRED

## Resume note
```

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
## Preserved human edits and conflicts
## Human notes
```

### `literature-set.md`

```md
---
kind: layered-literature-set
schema: 1
intent_revision: 0
updated: YYYY-MM-DD
---

# Layered Literature Set

## Anchor/core
## Extension
## Background/definition
## Controversy
## Preserved human edits and conflicts
## Human notes
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
