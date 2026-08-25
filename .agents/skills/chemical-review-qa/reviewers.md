# QA Reviewers

QA invoked 后，主会话请四个 fresh sub-agent 分别阅读同一版 brief、Research evidence、Synthesis handoff 和 `draft.md`。每个 reviewer 只收到自己的 role instructions、完成角色所需的同一份 allowlist 和最小 stage summary；不共享其它 reviewer 报告，也不读取隐藏 context、历史、memory、凭据或 sibling checkout。

四个默认角度是：

1. **evidence-locator**：来源 identity、原始 PDF locator、引用和 `SOURCE_FACT` 是否相互支持；
2. **chemistry-comparability**：底物/体系、催化剂状态、配体、条件、终点、对照和机制证据是否真的可比；
3. **synthesis-rebuttal**：比较、解释、反驳、矛盾结果和可检验假设是否有说服力；
4. **overclaim-counterexample**：范围漂移、过度确定性、反例、UNKNOWN 和 Chemical GAP 是否被诚实保留。

每份报告至少写 claim/paragraph location、applicable locator（没有就明确缺失）、severity、rationale、confidence、earliest return stage 和 suggested action；没有问题就写检查范围。缺失、超时、malformed 或 context-insufficient 输出写 `Incomplete QA` 和具体原因。reviewer cannot edit `draft.md` 或 upstream canonical artifact，不读其它报告，也不替研究者宣布科学有效。
