# Review Writer — Chemical Review plugin

这是 Chemical Review 的唯一开发源码仓。仓库同时维护一个可验证的
`plugins/chemical-review/` Codex plugin 发布单元，但它不是把整个开发仓
直接当成用户产品。

## 当前定位

当前版本目标是 `0.1.0-beta.1`：实验性、可人工迭代的化学文献综述研究同伴。
它可以帮助研究者从主题出发，经过

`Grill → Research → Prototype → PRD → Issues → Implement → Review`

逐步形成干净稿、研究者标注版、审查报告和候选投稿包；它不证明科学有效性、不复现实验、
不预测期刊接收，也不取代人类科学编辑。

## 源码与 plugin 边界

- **唯一 canonical source**：`.agents/skills/chemical-review/`
- **发布 projection**：`plugins/chemical-review/skills/chemical-review/`
- **plugin manifest**：`plugins/chemical-review/.codex-plugin/plugin.json`
- **项目本地 marketplace**：`.agents/plugins/marketplace.json`
- **同步命令**：`python scripts/build_plugin.py`

发布 projection 是由脚本生成的，不要直接编辑。CI 会运行
`python scripts/build_plugin.py --check`，发现源码与 plugin 不一致时阻止发布。

这样开发者仍可在 `.agents/skills/` 中使用项目级 skill；普通用户获得的是边界干净的
Chemical Review plugin，不会携带测试、fixtures、其他开发 skills、Playwright 上下文或本地
凭据。

## 从 clone 开始做人工 E2E

```bash
git clone https://github.com/kenqia/review-writer-skill.git
cd review-writer-skill
python scripts/build_plugin.py --check
python scripts/validate_plugin_package.py
python -B scripts/smoke_plugin.py
```

在 Codex 中将 clone 作为本地 repo marketplace 添加，然后安装 plugin：

```bash
codex plugin marketplace add /absolute/path/to/review-writer-skill
codex plugin add chemical-review@review-writer-skill
```

固定版本发布后，也可以让 Codex 直接从 GitHub tag 获取 marketplace：

```bash
codex plugin marketplace add kenqia/review-writer-skill --ref v0.1.0-beta.1
codex plugin add chemical-review@review-writer-skill
```

安装后新建一个 Codex task，让新 task 载入 plugin，然后使用：

```text
/chemical-review
```

第一次可用这个窄化主题：

```text
ligand effects in nickel-mediated C–C coupling
```

按 Grill 回答研究问题、范围/排除项、目标读者和预期贡献；Research 生成七条检索路径和分层
文献集；Prototype 测试跨论文比较、解释、反驳或新问题；随后调整 PRD、Issues 和 Implement。
Review 最终从同一 `review-content.md` 生成：

- `clean-manuscript.md`：没有内部标注的干净正文；
- `researcher-review.md`：带主张层级、证据 ID 和来源单元的研究者版；
- `review-report.md`：价值、化学推理、科学诚信、意图对齐和格式适配审查；
- `submission-candidate-package.md`：交给人类科学编辑继续核验的候选包。

人工修改或自然语言意见会被记录，并路由回最早受影响的阶段。用户不需要编辑内部 JSON。

## Research 工具边界

Research 默认只有真实的 OpenAlex discovery adapter；其他路线通过可替换 adapter 注入。推荐
路线是 OpenAlex/Semantic Scholar/Crossref → PubChem/ChEBI → Unpaywall/Europe PMC/CORE →
MinerU/GROBID/Docling。缺少 API、配额受限或全文受限时，流程必须保留降级信息，必要时请求
用户提供 DOI、题录、合法全文或授权 PDF；摘要、排名、解析器输出和模型推断都不能伪装成文献事实。

## 验证与发布

本地验证：

```bash
python -m unittest discover -s tests -p 'test_*.py'
ruff check .agents/skills/chemical-review plugins/chemical-review/skills/chemical-review scripts tests
python scripts/package_plugin.py
```

plugin manifest 也应使用 Codex plugin validator 检查；本机可运行：

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/chemical-review
```

正式发布顺序是：PR/CI 通过 → 合并到 `main` → 固定版本 tag（例如 `v0.1.0-beta.1`）→ GitHub
Release 自动生成 plugin zip 与 SHA-256 校验文件。发布 workflow 不把 Beta 版本包装成科学有效性或
期刊接收结论。

## 许可证

本项目及 Chemical Review plugin 使用 MIT License。`.agents/skills/` 中复用的第三方工程 skills
仍按 `LICENSES/mattpocock-skills-MIT.txt` 和 `THIRD_PARTY_NOTICES.md` 单独标明来源与许可。
