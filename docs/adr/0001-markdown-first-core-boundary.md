# Chemical Review 的 Markdown-first 核心边界

Status: accepted

Chemical Review 的核心产品采用独立、Markdown-first、无内置 provider runtime 的 skill：Intent、Research、Framework、Synthesis 和 QA；阶段结果摘要用于同会话连续推进、跨会话恢复和受限 sub-agent 上下文，但不形成额外的 handoff 仪式。Delivery（图表、DOCX、期刊适配）独立于核心科学流程，高影响 checkpoint 保留研究者决定而不引入全面状态机。这样保留证据、人工判断和恢复能力，同时避免 provider、orchestrator 和格式交付重新污染核心 skill。Framework 与 Publication 的边界由后续 ADR 细化。
