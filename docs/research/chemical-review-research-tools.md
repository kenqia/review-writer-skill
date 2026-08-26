# Chemical Review Research route

当前 Research 是 Markdown-first 的轻量协作路线，不提供内置 provider adapter 或阶段 runner。入口和 companion 文档位于：

- [`../../.agents/skills/chemical-review-research/SKILL.md`](../../.agents/skills/chemical-review-research/SKILL.md)
- [`../../.agents/skills/chemical-review-research/preflight.md`](../../.agents/skills/chemical-review-research/preflight.md)
- [`../../.agents/skills/chemical-review-research/discovery-and-screening.md`](../../.agents/skills/chemical-review-research/discovery-and-screening.md)
- [`../../.agents/skills/chemical-review-research/evidence-and-handoff.md`](../../.agents/skills/chemical-review-research/evidence-and-handoff.md)

Research 可以根据项目环境和研究者授权，协助使用 OpenAlex、Semantic Scholar、Crossref、PubChem、ChEBI、Unpaywall、Europe PMC、CORE、MinerU 或其它工具；这些是可替换的外部能力，不是 plugin 内置实现。预检应报告实际通过/失败、影响和配置入口，不能把名称列表当成可用性证明。

原始 PDF 仍是来源权威。解析文本先作为 `SOURCE_EXCERPT`，只有对照原文和 locator 后才写 `VERIFIED_SOURCE_FACT`。需要登录、机构权限或授权不清的全文，提供合法下载路径和用户等待动作。
