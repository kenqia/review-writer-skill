---
name: chemical-review-qa
description: "Run isolated multi-angle QA on a chemistry review draft and preserve revision conflicts."
---

# Chemical Review QA

读取同一版 `review-brief.md`、Research 证据和 `draft.md`，为四个固定、干净上下文角色各写一份独立报告：证据/locator、化学可比性/机制、综合新颖性/反驳、过度主张/反例。报告拥有 cited locator、severity、rationale 和 earliest return stage；角色不能读取其他报告或修改 draft。

arbiter 在所有报告完成后写 QA-owned `qa/review-report.md`、`qa/qa-plan.md`、`qa/revision-plan.md`，保留冲突，不做多数投票，不替人类作科学接受决定。QA rerun 创建新 round，旧报告保留。

`prepare` 只建立隔离上下文，不代表审查已经执行。调用方必须为返回的四个目录分别启动独立 reviewer（每个 reviewer 只读自己的 `context.md` 和 `role-instructions.md`，写自己的 `report.md`），禁止 reviewer 互读报告；四份报告齐全后，才调用 `finalize` 作为 arbiter。`write_fixture_reports` 仅供自动化测试，不能作为产品审查完成的证明。

```bash
python qa.py prepare --project /path/to/project
python qa.py finalize --project /path/to/project
python qa.py feedback --project /path/to/project --text 'The core claim needs a missing full-text source.'
```
