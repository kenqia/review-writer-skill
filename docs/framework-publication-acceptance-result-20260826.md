# Framework and Publication seam acceptance result — 2026-08-26

这是在既有 fresh-project fixture 上补充的受控 Product Use 材料。它验证 Framework 的证据到判断 seam，以及 Publication 的 Markdown projection、视觉边界和 DOCX 人类验收契约；不宣称完成真实化学研究、科学有效性或期刊接收。

## Fixture scope

- Framework：confirmed brief、Research handoff/evidence ledger、稳定 source identity 和 locator 的 MinerU 表示，以及明确 allowlist；材料覆盖兼容终点、冲突/负结果、独立重复、跨领域字段、无共同终点和证据不足返回。
- Publication：带有 `SOURCE_FACT`、`MODEL_SYNTHESIS`、`MODEL_HYPOTHESIS`、`UNKNOWN`、`NOT_COMPARABLE`、Chemical GAP、partial-scope 和流程元数据的 canonical `draft.md`，以及清理后的 `journal-manuscript.md`。
- Visuals/journal：一个来源关系完整的 Figure、一个不明来源的跨论文 composite、无目标期刊中性路径和目标期刊待确认路径。
- DOCX：fixture 只记录宿主生成后的人工检查契约；没有伪造一个宿主未实际生成的 Word 文件。

## Observed seam

| Slice | Result | Evidence |
| --- | --- | --- |
| Compatible comparison | PASS | `framework/evidence-matrix-compatible.md` preserves the universal spine, organic fields, denominator, conditions, locators, limitations and boundaries. |
| Domain generalization | PASS | `framework/domain-modules.md` uses separate organic, materials, analytical and chemical-biology fields without making any one module universal. |
| Judgment-changing cases | PASS | `framework/case-cards.md` includes a controlled positive contrast, conflict, negative/boundary case, independent repetition, alternative explanations and next tests. |
| Comparison relationships | PASS | `framework/comparison-map.md` records agreement, contradiction, extension, replication, boundary and `NOT_COMPARABLE` without an automatic ranking. |
| No-common-endpoint mode | PASS | `framework/no-common-endpoint.md` produces an evidence map, research typology and local explanation chains, with explicit non-comparability and Chemical GAP. |
| Insufficient evidence | PASS | `framework/insufficient-evidence.md` says no defensible framework yet and gives the earliest targeted Research action. |
| Framework handoff | PASS | `framework/framework-handoff.md` records scope, completed/reusable assets, boundaries, researcher decision and next recommendation. |
| Publication cleanup | PASS | The projection removes MinerU/parser, attachment, QA routing, Evidence ID and stage/unit metadata while preserving limitations, uncertainty, citations and partial scope in ordinary language. |
| Visual asset boundary | PASS | `publication/visual-assets.md` retains only the source-linked Figure 1 and excludes the ambiguous cross-paper composite; no new visual is created. |
| Journal branches | PASS | `publication/neutral-path.md` and `publication/target-journal.md` keep neutral output separate from the confirmation-before-official-guidance branch. |
| DOCX contract | HUMAN_ACCEPTANCE REQUIRED | `publication/docx-acceptance.md` requires an openable Word file generated from the exact Markdown projection and records the honest host-unavailable fallback. |

## Layered result

| Layer | Result | Boundary |
| --- | --- | --- |
| Document/package engineering | OBSERVED PASS | Canonical/plugin Markdown bundle, fixture files, projection checks and package tests are exercised separately. |
| Product Use | OBSERVED — CONTROLLED FIXTURE | The Framework and Publication seams are readable and recoverable from allowlisted artifacts; this does not replace a real chemistry run. |
| HUMAN_ACCEPTANCE | PENDING | A researcher must inspect the actual source PDFs, chemical judgments, generated DOCX and visual attribution. |
| Scientific validity | NOT_ASSERTED | Fixture content is synthetic and does not establish a chemical conclusion. |
| Journal acceptance | NOT_CLAIMED | The product does not predict or submit to a journal. |

The fixture deliberately keeps `draft.md` separate from the clean projection. Any scientific edit found in Markdown or DOCX returns to canonical `draft.md`; the projection is never a second source of truth.
