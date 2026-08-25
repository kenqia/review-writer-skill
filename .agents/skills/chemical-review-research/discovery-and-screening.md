# Research Discovery & Screening

围绕 confirmed brief 找候选，而不是把 brief 原句整段交给检索服务。可以从定义/同义词、方法/材料、关键事件、引用关系、作者团队、领域边界和近期进展等互补路径开始；新线索出现时，调整下一轮词和路径。每条路径都说明它覆盖哪个 core claim、带来什么新信息，以及是否因失败而留下空白。

在 `research/search-log.md` 留下简短记录：查了什么、何时查、哪条路径有效、哪里失败、raw hit 数量、去重方式、为什么继续或停止。provider 返回的是线索，不是来源事实。保留 raw hits 与 deduplicated candidates 的关系，不要只留下最终列表。

候选笔记至少让人看出稳定 identity（stable identity：DOI、PMID、版本或人工确认）、标题/年份、与哪条 core claim 有关、为什么可能纳入以及不确定之处。重复版本合并时保留出处关系；无法可靠绑定就写 `UNKNOWN identity`。在 `research/candidates.md` 或等价 Markdown 中保留检索路径、identity、筛选理由、证据角色和 coverage 标记。

把候选分成 `INCLUDE`、`EXCLUDE` 或 `MAYBE`，每项都写具体理由，并说明 `primary`、`secondary`、`background` 或 `excluded` 的暂定角色。标题相似但化学对象不符的论文、没有论点关联的背景材料和未验证摘要不要悄悄升级成 primary evidence。

通常把 review-only、materials background、docking-only、protein-design、generic-AI、workshop/preprint 以及研究对象不匹配的条目留在背景或排除栏，除非研究者在 brief 中明确给了它们位置。reviews、背景综述、材料背景、docking-only、protein-design、generic-AI 或仅有摘要的记录不能因 metadata 相似而获得 primary 角色。

## 候选集交接

把当前集合、raw→deduplicated 关系、路径 coverage、覆盖到的论点、明显缺口、可能的 false-positive 和下一条检索建议展示给研究者。研究者可以：

- `accept_candidates`（或用普通语言接受）：继续安排相关全文；
- `return_to_discovery`：补 query、边界或候选；
- `pause`：先停下来。

接受只针对当前集合；brief、范围或候选发生实质变化时，重新展示即可。停止依据是核心论点覆盖、路径边际收益和重要未覆盖区域，不是固定论文数量。候选仍然是 discovery material，只有下一份 candidate-acceptance 记录明确接受后才可进入全文路线。
