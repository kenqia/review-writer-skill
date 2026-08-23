# review-writer-skill

Project scaffold for developing a chemical literature review agent skill.

## Engineering framework

This repository contains project-scoped, editable copies of the stable engineering and productivity skills from [mattpocock/skills](https://github.com/mattpocock/skills).

- Skills: `.agents/skills/`
- Upstream source lock: `skills-lock.json`
- Agent configuration: `AGENTS.md`
- Issue tracker: GitHub Issues
- Triage vocabulary: `docs/agents/triage-labels.md`
- Domain documentation: single-context, configured by `docs/agents/domain.md`

Product requirements and chemistry domain terminology have not yet been defined. They will be developed through the installed specification and domain-modeling workflow.

## Chemical review skill

The first product slice is the user-invoked `chemical-review` skill. It starts from a chemistry review topic, persists a human-readable intent/domain/workflow state, and routes later Research, Prototype, PRD, Issues, Implement, and Review phases through one orchestrator seam.

- Entrypoint: `.agents/skills/chemical-review/SKILL.md`
- Workflow contract: `.agents/skills/chemical-review/WORKFLOW.md`
- State templates: `.agents/skills/chemical-review/ASSET-TEMPLATES.md`
- Minimal file orchestrator: `.agents/skills/chemical-review/orchestrator.py`
- Research capability adapters: `.agents/skills/chemical-review/research.py`
- Prototype and blueprint behavior: `.agents/skills/chemical-review/prototype.py`
- Dependency-aware research/writing units and central merge: `.agents/skills/chemical-review/units.py`
- Multi-layer Review and synchronized dual-track delivery: `.agents/skills/chemical-review/review.py`
- Human-feedback routing and safe iterative resume: `.agents/skills/chemical-review/feedback.py`
- Public tool-boundary notes: `docs/research/chemical-review-research-tools.md`
