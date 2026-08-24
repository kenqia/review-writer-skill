---
name: chemical-review-intent
description: "Turn a chemistry review topic into a confirmed review-brief.md handoff."
---

# Chemical Review Intent

独立入口：接收主题或研究想法，创建并维护项目根目录的 `review-brief.md`。

Intent 独占综述问题、核心论点候选、范围、排除项、读者、预期贡献、证据标准和边界场景。首次 topic-only 输入只生成带 Open question 的草案；Research 只能消费 `confirmed: true` 的 brief。已确认 brief 的变化先写 `review-brief.proposed.md`，必须得到明确确认后才替换当前 brief。

下一阶段：确认后运行 `$chemical-review-research`。

CLI 示例：

```bash
python intent.py init --project /path/to/project --topic 'nickel-mediated C-C coupling'
python intent.py confirm --project /path/to/project --decisions-json decisions.json
python intent.py propose-change --project /path/to/project --changes-json changes.json
python intent.py confirm-change --project /path/to/project
```

Intent 不导入旧 `chemical-review` orchestrator、Prototype/PRD/Issues/Implement payload，也不写 Research、Synthesis 或 QA 资产。
