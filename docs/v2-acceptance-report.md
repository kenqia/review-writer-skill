# Chemical Review acceptance boundary

Updated: 2026-08-25

当前包的产品边界是 Markdown-first、轻量、可读和可回滚。完整 fresh-project document-boundary runbook 见 [`v2-fresh-project-acceptance.md`](v2-fresh-project-acceptance.md)。以下结论只描述工程包，不把它冒充成真实科学综述：

| Boundary | Result | Evidence / limitation |
| --- | --- | --- |
| Markdown bundle | PASS | 五个核心 skill 与独立 Publication 都由 `SKILL.md`、companion Markdown 和 agent manifest 构成。 |
| Plugin projection | PASS | canonical source 与 `plugins/chemical-review/` 可由 build check 对齐。 |
| Static package checks | PASS | manifest、发布文件边界和 cold-start smoke 可在本地验证。 |
| Product Use | OBSERVED — CONTROLLED FIXTURE | 基础 fresh-project run 与 Framework/Publication seam fixture 均已记录；真实主题 Product Use 和宿主 DOCX 能力仍需单独验收。 |
| HUMAN_ACCEPTANCE | PENDING | 研究者仍需检查 brief、原始 PDF、证据 locator、draft 和 QA 冲突。 |
| Scientific validity | NOT_ASSERTED | 本项目不认证化学结论、证据穷尽性、投稿准备度或期刊接收。 |

安装包不包含阶段 runner 或 provider runtime。`scripts/` 仅用于打包与静态检查；后续如果需要接入工具，应以独立、可替换的能力说明加入，而不是把 Markdown 流程改回强脚本状态机。

Framework 与 Publication 的补充 fixture 结果见 [`framework-publication-acceptance-result-20260826.md`](framework-publication-acceptance-result-20260826.md)。
