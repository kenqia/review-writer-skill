# Review Writer — Chemical Review

Chemical Review 是一个轻量的化学文献综述 skill 包。它用自然语言 Markdown 帮助研究者把想法变成可讨论的 brief、证据笔记、候选正文和 QA 反馈；不依赖阶段 runner、脚本状态机或 provider 接入，也不替研究者做最终科学判断。

## 包的形状

源码和发布 projection 都只包含 Markdown 规则与 agent manifest：

```text
chemical-review-{intent,research,synthesis,qa}/
├── SKILL.md                 # 这一阶段做什么、何时读取下面的文档
├── Markdown companion         # 该阶段的步骤、角色或交接规则
└── agents/openai.yaml       # 展示名和默认提示
```

`.agents/skills/` 是 canonical source，`plugins/chemical-review/` 是发布 projection。`scripts/` 只负责同步、打包和检查文件，不参与综述运行。

## 使用方式

在 Codex 中按需显式调用：

```text
$chemical-review-intent
$chemical-review-research
$chemical-review-synthesis
$chemical-review-qa
```

没有必要一次调用全部阶段。每个阶段都可以先读自己的 `SKILL.md`，再按它指向的 companion 文档工作，并用普通语言把结果交回研究者。

## 四个阶段

Intent 按 `grilling.md` 逐轮提出带推荐答案的 frontier 问题，并用 `brief-contract.md` 区分模型建议、用户回答、默认值和 `UNKNOWN`；`domain-modeling.md` 只在术语真正需要澄清时加载，`result-and-revision.md` 负责可读结果摘要与 revision snapshot。研究者明确确认 shared understanding 后才写 `review-brief.md`；需要时再加载 `expert-review.md` 请 fresh sub-agent 做 advisory review。它只是建议，不接 provider，也不改 canonical brief。

Research 按语义需要读取 `preflight.md`、`discovery-and-screening.md`、`candidate-acceptance.md`、`full-text-and-resume.md`、`evidence-and-handoff.md`。先把网络、检索、合法全文和解析能力做一个简短的可用性检查；缺配置时说明影响和官方配置入口，`configure_and_continue` 只表示配置后回来，不能偷偷开始正式研究。正式开始、候选集和 handoff 都用 Markdown 与用户确认。缺全文时给合法下载路径和放置位置，不绕过访问控制；解析摘录在原始 PDF 和 locator 核验前不能成为来源事实。

Synthesis 读取 `planning.md`、`drafting.md`、`handoff.md`。先提出轻量写作计划，再以 `draft.md` 作为唯一内容基线，按需要生成读者版和研究版。来源事实、模型综合、假设、UNKNOWN、NOT_COMPARABLE 和 Chemical GAP 要说清楚，但不需要内部 payload 或程序字段。

QA 读取 `reviewers.md`、`arbiter.md`、`revision-routing.md`。主会话可开四个互不污染的 fresh sub-agent，分别看证据定位、化学可比性、论证反驳和过度主张；arbiter 汇总冲突，研究者用普通语言决定接受、拒绝、暂缓以及返回哪个阶段。QA 不投票、不自动改稿。

### 上下文边界

尽量不要在全局或父目录约定中强制模型读取与当前综述无关的 memory、历史项目、旧 workflow 或凭据。只加载当前项目、当前阶段及用户明确允许的材料；需要额外背景时由研究者点名。这样能让本 skill 的自然语言规则保持足够权重。

### 证据边界

文档建议保留来源 identity、locator、比较口径和未知项，并把具体来源事实与模型推断分开。它们是帮助研究者复核的轻量护栏，不是把每一步锁成二进制 gate；对来源、全文和科学结论的最终接受仍由人类研究者决定。

## 本地检查

```bash
python scripts/build_plugin.py --check
python scripts/validate_plugin_package.py
python -m unittest discover -s tests -p 'test_*.py'
python -B scripts/smoke_plugin.py
```

这些命令只验证 Markdown bundle、manifest 和发布边界；它们不会启动 Chemical Review，也不会声称完成一次真实文献综述。公开 fresh-project 文档边界验收的 runbook 见 [`docs/v2-fresh-project-acceptance.md`](docs/v2-fresh-project-acceptance.md)。

## 许可证

本项目及 Chemical Review plugin 使用 MIT License。
