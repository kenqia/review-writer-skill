---
name: chemical-review-qa
description: "Run isolated multi-angle QA on a chemistry review draft and preserve revision conflicts."
---

# Chemical Review QA

读取同一版 `review-brief.md`、Research 证据和 `draft.md`，为四个固定、干净上下文角色各写一份独立报告：证据/locator、化学可比性/机制、综合新颖性/反驳、过度主张/反例。报告拥有 cited locator、severity、rationale 和 earliest return stage；角色不能读取其他报告或修改 draft。

arbiter 在所有报告完成后写 QA-owned `qa/review-report.md`、`qa/qa-plan.md`、`qa/revision-plan.md`，保留冲突，不做多数投票，不替人类作科学接受决定。QA rerun 创建新 round，旧报告保留。

```bash
python qa.py prepare --project /path/to/project
python qa.py finalize --project /path/to/project
python qa.py feedback --project /path/to/project --text 'The core claim needs a missing full-text source.'
```
