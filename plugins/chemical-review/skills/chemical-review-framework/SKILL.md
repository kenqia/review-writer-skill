---
name: chemical-review-framework
description: "Turn locator-bound chemistry evidence into a generalized, testable judgment framework before synthesis."
disable-model-invocation: true
---

# Chemical Review Framework

Framework 是 Research 与 Synthesis 之间的化学判断工作台。它的目标不是再列一次论文，而是把多个具体研究压缩成有边界、可检验、能指导实验或后续研究的判断框架。它是一个独立入口；在同一会话中可承接 Research，也可以在另一轮只凭持久化的阶段摘要和用户 allowlist 重新调用。

## 输入边界与产物

默认只读取：

- 研究者已经确认的 `review-brief.md`；
- Research handoff、evidence ledger、已接受的候选/文献集和 Research result summary；
- 在来源 identity 正确、stable identity（稳定身份）可靠且 locator 可追溯时可信的 MinerU 来源文本、表格和图注；
- 研究者明确列出的其它材料。

不要主动读取全局 memory、隐藏 history、无关 parent context、凭据、cookie、session、sibling checkout 或未列入 allowlist 的旧稿。缺材料时报告缺口，不从聊天残留中猜补。Framework 不负责发现论文、获取受限全文或替 Research 核验来源；它是一个 independent entry（独立入口），不是 Research 的替代品。

Framework 默认拥有并写入这些人类可读的 Markdown 资产：

1. `evidence-matrix.md`：条件完整、可追溯的比较主表；
2. `case-cards.md`：真正改变判断的案例卡；
3. `comparison-map.md`：研究之间的关系图谱；
4. `judgment-framework.md`：解释链、边界和可检验预测；
5. `framework-handoff.md`：给 Synthesis 或下一轮 Framework 的阶段结果摘要。

这些是默认产物而不是固定 schema、固定行数或固定篇幅。Research owns 来源、候选、解析和 evidence ledger；Framework owns 上述比较和判断资产；Synthesis 拥有 `draft.md`。Synthesis reads Framework 的结果；下游可以读取上游资产，但 do not silently rewrite 上游 canonical artifact。

## 渐进读取

先读取本页，再按当前任务需要读取：

1. [`intake-and-spine.md`](intake-and-spine.md)：材料边界、MinerU 信任边界、通用比较主轴和 brief 驱动的领域模块；
2. [`cases-and-comparison.md`](cases-and-comparison.md)：判断改变型案例、案例卡和跨研究比较关系；
3. [`judgment-and-boundaries.md`](judgment-and-boundaries.md)：解释链、非比较模式、Chemical GAP 和价值检查；
4. [`handoff-and-revision.md`](handoff-and-revision.md)：交接、恢复、返 Research/Synthesis 和修订边界。

不要为了“完整”预先加载全部 companion。某一页的线索不等于相应资产已经完成。

## 推荐工作回合

1. 先核对 confirmed brief、Research handoff 和 allowlist，写明本轮的输入范围与缺失材料。
2. 建立通用比较主轴，再从 brief 生成适用的领域模块；不要先套用催化、材料、药化或其它单一领域表格。
3. 逐项记录来源观察、条件、对照、终点、locator、限制和混杂因素；保留 `UNKNOWN`、`NOT_COMPARABLE` 和 `Chemical GAP`。
4. 选择 judgment-changing cases（会改变判断的案例），形成案例卡和关系图；解释一致、冲突、边界、重复与不可比，而不是按论文数量平均抽样。
5. 用证据、反例/替代解释、适用范围和可检验问题形成判断框架；没有共同终点时切换到证据地图和局部解释链。
6. 写 framework handoff，让研究者看到本轮完成了什么、还不能声称什么，以及下一步应进入 Synthesis、返回 Research 还是补充 allowlist。

## 轻量 checkpoint

Framework 默认建议用于包含跨研究化学判断的综述。背景说明、文献目录和证据审计可以由研究者明确跳过；跳过后仍可写作，但不得把产物称为完成了完整批判性综合。进入 Synthesis 前，研究者应明确接受当前 Framework 边界，或清楚说明只需 partial-scope 结果。

Framework 不以固定论文数、案例数、矩阵行数、字数或 query 数宣布完成。无法形成可辩护框架时，必须如实写出 `RESEARCH_GAP`（research gap）或等价的普通语言，并给出最早且具体的返回 Research 动作。能力可用性、provider 名称和脚本输出不是化学判断的替代物。

完成 Framework 表示：证据主表、案例、比较关系、判断/边界和 handoff 都可读，重要主张能回到 source identity（来源 identity）与 locator，研究者知道哪些是来源事实、哪些是模型综合或假设。只生成表格、摘要或一段解释不等于完成。如果尚不能形成 no defensible framework（可辩护的判断框架），必须把这个结果写明。
