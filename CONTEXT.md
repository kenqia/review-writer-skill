# Chemical Review

Chemical Review 是一个轻量、可组合的化学文献综述 skill 包。它帮助研究者提出问题、整理证据、写出候选综述并收集反馈；Markdown 交接是产品本身，用户判断是科学决策的来源。

## 五个核心入口与一个可选交付入口

- **Intent**：用一轮一轮的 grill 收敛 research question、core claims、scope、exclusions、audience、contribution 和 evidence expectations，最后由研究者确认 `review-brief.md`。
- **Research**：围绕 confirmed brief 发现候选、记录合法全文路线、整理 locator-bound evidence，并用一份自然语言 handoff 说明覆盖与缺口。
- **Framework**：读取 Research 的可信来源文本，把多篇研究组织成通用比较主轴、领域模块和可检验的化学判断框架；它位于 Research 与 Synthesis 之间。
- **Synthesis**：先讨论写作计划，再以唯一的 `draft.md` 写出批判性综合；读者版和研究版是同一基线的视图。
- **QA**：用隔离的 fresh reviewer 角色检查证据、化学可比性、论证反驳和过度主张，再把反馈交回研究者。

每个入口只依赖自己的 `SKILL.md` 和 companion Markdown。没有中央 orchestrator、阶段 runner、隐藏 payload 或必须安装的 provider。

## 产品边界与执行语义

**核心五 skill**：Intent、Research、Framework、Synthesis 和 QA 组成 Chemical Review 的核心科学协作面，分别负责意图、证据、化学判断框架、综合和审查；DOCX 与期刊适配属于独立的 Delivery 能力，不是核心研究阶段。

**Delivery 能力**：把已确认的研究材料投影为图表、DOCX 或期刊适配交付物的后续能力。Delivery 不改变核心证据、brief 或正文权威。

**Research 协议**：Research skill 对发现、合法全文、解析和证据交接提供自然语言工作协议；它可以使用环境中真实可用的外部能力，但不把某个 provider 或 adapter 作为核心产品依赖。

**Evidence-bounded value check**：Framework 中的轻量价值检查，用少量已绑定证据判断是否存在非摘要式的比较、解释、反驳或可检验问题；它不再作为独立入口，也不是默认硬闸门。

**Chemical judgment framework**：把多篇具体化学研究压缩为有边界、可检验、能指导实验或研究决策的判断框架；它不仅整理证据，还要显式表达比较关系、机制/因果解释、反例、适用边界和下一步可检验预测。其比较字段由项目 brief 和领域语境决定，不把某一化学子领域的字段硬套到所有主题。

**Framework 运行语义**：对包含跨研究化学判断的综述，默认建议在 Research 与 Synthesis 之间运行；纯背景说明、文献目录或证据审计可以明确跳过。跳过时不应把产物表述为完成了完整批判性综合。

**Framework 资产所有权**：Research 拥有来源、解析文本、候选和 evidence ledger；Framework 拥有证据矩阵、案例卡、比较关系和判断框架；Synthesis 读取 Framework 结果但不静默改写；Publication 只生成投影，不回写任何核心科学资产。

**Framework 默认输入**：confirmed brief、Research handoff、Research evidence ledger、候选/文献集、MinerU 解析产物和用户明确 allowlist 的材料；隐藏上下文、全局 memory、无关历史、凭据、cookie、sibling checkout 和未列入 allowlist 的旧稿不属于输入。

**通用比较主轴**：Framework 跨化学主题共享的最小比较语言，包括研究对象/体系、变量或干预、实验/计算情境、对照、终点、观察结果、证据定位、限制、混杂因素和适用边界；具体字段由 brief 驱动的领域模块补充。

**Framework 证据状态**：`TRUSTED_SOURCE_TEXT` 表示 identity 正确且 locator 可追溯的可信 MinerU 来源表示；`SOURCE_OBSERVATION` 表示来源直接报告的观察；`AUTHOR_HYPOTHESIS`、`MODEL_SYNTHESIS` 和 `MODEL_HYPOTHESIS` 保留解释与推断的性质。`VERIFIED_SOURCE_FACT` 可以表示额外的原始 PDF 核对，但不是 Framework 的前置门槛。

**Framework 非比较模式**：当不同研究没有共同终点或关键条件不足以横向排序时，Framework 输出证据地图、研究类型学、局部解释链和不可比较边界，不强行生成统一排名或伪比较表。

**Framework 最低质量标准**：不以固定论文数、案例数、表格行数或字数作为门槛；至少应尝试形成一个有具体证据支撑的判断、类型学或边界说明，并记录比较对象/终点、反例或替代解释、适用范围和可检验问题。无法形成时，明确报告尚未形成可辩护框架并建议返回 Research。

**解释链**：把变量、情境、可观察终点、解释关系、适用边界和可检验预测连接起来的推理结构；“机制”只是反应和分子过程主题中的一种解释链，不是所有化学综述的默认术语。

**改变判断的案例**：因为有清晰对照、冲突结果、负结果、独立重复、适用边界或实验启示，能够改变核心论点或暴露其风险的研究；Framework 按此价值选择案例，不按固定论文数平均抽样。

**Trusted MinerU source text**：本项目对 MinerU 解析产物的工作假设：在来源 identity 正确且 locator 可追溯时，可将其视为原文的可信文本/表格表示，不再因 parser excerpt 状态阻止证据整理；该假设不等同于自动证明作者机制解释、跨论文比较或模型综合正确。

**Publication-clean projection**：由用户主动调用的交付投影，将已确认的 Markdown 草稿整理为普通期刊可读文本和 DOCX；移除内部标签、MinerU/附件/QA 路由等流程元数据，但把重要不确定性和证据限制改写为正常科学表述，不回写核心正文权威。

**Publication editorial boundary**：Publication 可以清理标签、重排结构、改善表达和整理表格/引用，但不能新增未经证据支持的科学主张、静默删除重要限制、改变核心判断或把模型假设伪装成来源事实。

**Publication language boundary**：Publication 默认保持输入稿件的语言和术语体系，不把期刊化清理与翻译合并；翻译需要单独、明确的任务。

**Publication timing**：Publication 是用户主动调用的独立入口，可以在 QA 前后运行；QA 前的产物只能称为期刊化草稿，Research 或 Framework 不完整时必须保留自然语言科学限制。

**来源绑定视觉资产**：Publication 可以保留已有且来源、caption、locator 和引用关系明确的 Figure、Scheme 和 Table；不生成新的科学图，不把来源不清、跨论文拼接或未核验的视觉资产带入期刊稿。

**人类可读标签**：`READY_FOR_SYNTHESIS`、`WAITING_FOR_USER`、`RESEARCH_GAP`、`SOURCE_EXCERPT`、`VERIFIED_SOURCE_FACT`、`SOURCE_FACT`、`MODEL_SYNTHESIS` 和 `MODEL_HYPOTHESIS` 等短标签，用于 Markdown handoff、resume 和审查定位。标签不是隐藏状态机，也不是用户必须输入的命令。

**Intent 草案**：尚未得到研究者确认的研究意图工作材料；其中必须区分模型候选、用户回答、默认值和 `UNKNOWN`，不能被 Research 当作已确认意图。

**Confirmed brief**：研究者确认 shared understanding 后形成的下游意图权威，至少说明研究问题、核心论点候选、范围、排除项、读者/期刊、预期贡献和证据期望。

**Research 五模块链**：能力预检、Discovery、候选集接受、全文/证据处理和 Research handoff 这五个不可删的语义模块。它们可以拆成不同数量的 Markdown 文件，但不能把其中的工作隐去或合并成摘要式“已完成”。

**Formal Research start**：研究者在能力预检完成或明确接受已解释降级后，对正式 Discovery、全文和解析工作的单独确认；配置选择本身不等于开始研究。

**Revision/round**：对 brief、Research、draft 或 QA 的一次可追踪迭代。新一轮保留旧材料和人工修改，并从最早受影响的阶段继续，而不是静默覆盖或从头重做。

**语义 companion**：围绕一组相互依赖的研究决定、失败路线和完成标准组织的 Markdown 文档。companion 的数量由语义边界决定，不由固定的文件配额决定。

**阶段本地应用**：根 glossary 负责定义项目术语；每个 skill 自己说明这些术语在本阶段如何影响输入、判断、输出和暂停，不把流程规范隐藏在全局文档中。

**默认 allowlist**：skill 或 fresh sub-agent 默认只读取当前阶段的 canonical handoff、该阶段拥有的材料和用户明确列出的额外材料；未点名的历史、memory、父上下文、凭据和 sibling checkout 不属于默认输入。

**完成契约**：每个语义 companion 对何时读取、要完成的工作、暂停/继续条件、失败恢复、Markdown 产物以及“线索不等于完成”的区别作出自然语言说明。

**压力场景护栏**：把最容易误报成功或越权的场景直接写进相关 skill 文档，例如 metadata 不能成为正文事实、配置选择不能启动研究、reviewer 不能改稿或互读。它们是运行时提醒，不是隐藏测试状态。

**Artifact ownership**：每个核心阶段拥有自己的 canonical Markdown 材料并负责写入；下游可以读取上游材料，但不能静默改写上游权威。Delivery 只生成投影，不回写核心科学材料。

**Evidence ledger**：人类可读的来源、版本、访问依据、原始 PDF、locator、证据等级、比较字段和 limitation 记录。它可以按项目扩展，不等同于固定数据库 schema；机器索引只能作为辅助。

**Coverage stopping**：根据检索路径覆盖、边际新增价值和重要未覆盖区域决定是否建议停止当前 Research 轮次；不以固定论文数或 query 数作为科学充分性。

**Bounded delegation**：只有在角色、allowlist、读写边界和返回材料都明确时才委托 fresh sub-agent；worker 不能直接改动别人的 canonical artifact，失败或超时必须如实返回。

**Revision snapshot**：保留当前 canonical 文件、必要的旧版本快照和简短 revision/feedback 说明，使人工修改、拒绝/暂缓决定和返回最早阶段都可恢复；不把完整对话倾倒进项目。

**同会话连续推进**：主会话在高影响 checkpoint 得到确认后，可以直接进入下一个 skill，不重复举行阶段 handoff，也不重新读取无关历史。

**独立入口**：五个核心 skill 都可以单独被调用或重跑；独立调用以已持久化的阶段结果摘要和用户 allowlist 为输入，不依赖上一轮聊天记忆。Publication 是另一个用户主动调用的独立交付入口。

**自包含化学 companion**：Chemical Review 在自己的 bundle 内提供化学适配后的 interview、brief、术语和审查规则；它可以借鉴通用 skill 的方法，但不要求外部通用 skill 完整加载才能执行核心流程。

**Brief advisory**：在 confirmed brief 之后、研究者明确 opt-in 才启动的独立建议，不是 Research、QA、同行评审或科学认证。fresh reviewer 只接收 role prompt、confirmed brief 和明确 allowlisted material；它不浏览、不调用 provider、不读 hidden context、不编辑 artifact。finding 按 actionable brief module 分组，并包含 severity、rationale、suggested change、confidence 和 unresolved questions。研究者可 skip、accept selected、reject all 或 defer；接受项先形成 `UNCONFIRMED_PROPOSAL` 的 `review-brief.proposed.md`，经过第二次明确确认才可改变 canonical brief。timeout、unavailable、malformed 或缺少材料时，报告原因并保持 brief 不变。

**计划路线预检**：只对当前 brief 所需的最佳 Research 路线和有现实价值的备选路线做小型实际探针；provider 名称、配置字段或 doctor 输出本身不是能力证明。

**原始 PDF 核验**：主 agent 或研究者使用合法原始 PDF、稳定 identity 和精确 locator 对来源内容作证据级判断。项目约定 MinerU 在 identity 正确且 locator 可追溯时提供可信来源文本；仍需把来源观察与作者解释、跨研究综合和模型假设区分开。

**候选集接受**：研究者在全文成本和证据范围扩大前，对 discovery 候选的角色、纳入/排除理由、覆盖与误收风险作出的高影响决定。它不禁止后续增量发现。

**唯一正文权威**：Synthesis 的 `draft.md` 是唯一可持续修改的正文基线；`reader-draft.md` 和 `research-draft.md` 是由同一 revision 投影出的视图，不是第二正文数据库。

**重要 claim 表达**：重要比较、机制解释、趋势和新假设应让读者区分 `SOURCE_FACT`、`MODEL_SYNTHESIS` 和 `MODEL_HYPOTHESIS`，并在适用时保留 identity、locator、条件、对照、分母/测量口径和 limitation；普通连接句不需要逐句标记。

**Partial-scope candidate**：Research 不完整时仍可生成的候选稿，但必须明确标记 `unreviewed`、`evidence-bounded` 和 `partial-scope`，公开未覆盖区域与返回 Research/缩小范围的建议。

**QA isolation**：四个 reviewer 各自在 fresh context 中只读取自己的 role instructions、同一版 allowlist 材料和必要的阶段摘要；reviewer 不互读报告、不改 draft。

**Incomplete QA**：reviewer 缺失、超时、malformed 或无法访问必要材料时，QA 报告明确缺失角度，不能用其余报告冒充完整审查。

**QA finding**：至少包含 claim/段落定位、适用的来源 locator、severity、rationale、confidence、earliest return stage 和建议动作的可审查观察。QA 不输出科学 pass/fail，不自动改 draft 或推进 Delivery。

**阶段结果摘要的最小内容**：说明本轮输入范围、实际完成的工作、可复用产物、证据/推理边界、未解决问题、研究者已作决定、下一步建议和需要的高影响确认。它是恢复与独立调用材料，不是额外 handoff 仪式。

**高影响 checkpoint**：只包括会改变下游结果的意图确认、Research 授权/正式开始、候选集接受、Research 结果进入 Synthesis、Synthesis plan 开始 drafting、draft 进入 QA，以及核心意图/范围/证据标准变更。普通检索、解析、比较、修辞修订和 QA 准备不应被无故暂停。

**验收层级**：文档/包结构、Product Use、HUMAN_ACCEPTANCE、scientific validity 和 journal acceptance 是不同声明；任何一层的通过都不能代替另一层。

**宿主上下文边界**：skill 可以规定默认 allowlist、拒绝主动读取无关文件和 hidden history，但不能覆盖更高优先级的宿主系统指令。产品不承诺屏蔽已被宿主注入的全局指令，只承诺不主动扩大读取范围。

**语义模块命名**：设计阶段冻结模块职责、读取条件和完成契约，不提前冻结 companion 的具体文件名；文件拆分应服从真实语义边界和上下文需要。

## 轻量协作规则

1. 先读当前阶段的 `SKILL.md`，再按它指向的 companion 文档选择需要的步骤；不要预先加载整个仓库。
2. 对研究者真正需要做的取舍给出推荐，但把决定留给研究者；可以用普通语言改写，不要求填写内部 schema。
3. 在 brief、Research handoff、写作计划和 QA 反馈之间使用短 Markdown 交接。只有会影响下游理解的内容才持久化。
4. 需要额外来源或项目材料时，先请求或读取明确 allowlist；不要自动加载全局 memory、历史项目、无关 parent context、凭据或 sibling checkout。
5. 文档可以提示人类确认，但不把流程变成不可解释的程序状态机。只有来源真实性、合法访问和明显的证据越界值得硬提醒。

## 研究者能看到的资产

- `review-brief.md`：当前已确认的研究意图。
- `research/`：候选、下载说明、证据笔记和研究 handoff；缺全文时记录合法 URL、访问依据、目标目录和下一动作。
- `evidence-matrix.md`、`case-cards.md`、`comparison-map.md`、`judgment-framework.md`、`framework-handoff.md`：Framework 的证据矩阵、改变判断的案例、跨研究关系、解释链和结果摘要。
- `draft.md`：Synthesis 的唯一正文基线。
- `reader-draft.md` / `research-draft.md`：同一正文的不同阅读视图。
- `qa/`：独立 reviewer 报告、冲突汇总和 revision routing。
- `journal-manuscript.md` / `journal-manuscript.docx`：Publication 生成的期刊可读投影，不是第二份正文权威。

这些文件是可读的工作材料，不是数据库。数字、机制和强结论要能回到来源 identity 与 locator；不确定时写 `UNKNOWN`、`NOT_COMPARABLE` 或 `Chemical GAP`。

## 领域语言

**SOURCE_FACT**：原始来源在明确 locator 处直接支持的事实。
**MODEL_SYNTHESIS**：模型跨来源比较、解释或归纳的判断。
**MODEL_HYPOTHESIS**：可由后续实验或文献检验的推断。
**NOT_COMPARABLE**：比较主轴字段不足以支持排序或强比较。
**Chemical GAP**：当前证据范围无法回答、需要新来源或人工核验的缺口。

比较时通常关注底物/材料、催化剂状态、配体、条件、终点、测量口径和机制证据；具体项目可以删减或增加字段，不把示例字段变成全局硬 schema。

## 可选 brief 专家审查

Intent 确认 brief 后可以把 role prompt、confirmed brief 和用户明确 allowlist 的材料交给一个 fresh sub-agent。它只返回 advisory findings，不读隐藏上下文、不调用 provider、不改文件；主会话展示建议，研究者决定是否写入 proposed brief 并确认。它不是同行评审、科学有效性认证或期刊接收预测。

## 产品边界

这是研究协作材料，不是自动投稿器、科学真值机或期刊接受预测器。`scripts/` 中的 Python 仅用于同步、打包和静态检查；它们不拥有阶段状态，也不是用户入口。真实 provider、API key、cookie 和 session 不写入仓库、Markdown 或发布包。
