# 类似综述制作 skill / literature-review workflow 调查

调查日期：2026-08-24
调查对象：公开 GitHub 仓库中的官方 `README.md`、`SKILL.md`、源码和官方工具文档；以及本仓库与本机已有的 review-writing skills。
证据边界：以下结论是对项目**公开设计和代码契约**的核对，不等于这些项目在 Chemical Review 上已经通过科学有效性、完整性或人工验收。没有运行外部项目，也没有把博客、排行榜或搜索摘要当作项目行为证据。

## 结论先行

1. **我们不需要照搬另一个七/八阶段流程。** 最值得吸收的是四个正交能力：
   - STORM 的多视角提问与“先研究、再大纲、再写作”分离；
   - PaperQA2 的本地全文索引、metadata-aware retrieval、页码引用和媒体对象；
   - `research-paper-lifecycle-skills` 的来源验证、venue profile、可恢复状态和外部可验证质量门；
   - `slr-prisma` 的协议/筛选/计数/PRISMA 资产和 Word 输出思路。
   这些都要接入 Chemical Review 自己的 `VersionContext`、source registry、claim blocks 和化学 comparability 规则，而不是引入第二套权威。

2. **Research 的核心补强不是“再接更多搜索 API”，而是把发现、全文、解析和主张资格分开。** 外部项目普遍把 metadata、全文、引用验证或媒体解析拆成独立能力；PaperQA2 和 Shaishav 的 workflow 都把“来源解析/验证”作为后续门，而不是把题录直接当作证据。[S3][S8]

3. **图片能力应在 Research/规划阶段产生 inventory，而不是在最后一步临时插图。** PaperQA2 将图片/表格作为与文本 chunk 关联的媒体对象，并用合成 caption 帮助检索；Aut_Sci_Write 提供 Figure/Scheme/Chart 的 PDF 裁剪、子图识别和 600 DPI 输出；本仓库已有 paragraph-anchored figure candidate 和 final hard gate，可直接作为合并边界。[S3][S7][L4][L5]

4. **连续执行模式需要“批量执行 + 硬阻塞暂停”，不需要取消证据门。** Open Deep Research、GPT Researcher 和 `paper-assembly` 都用 supervisor/parallel units/状态传播来减少串行等待；Shaishav 的每阶段 sign-off 则适合 acceptance 模式，不应成为默认执行模式。[S4][S5][S8][S10]

5. **DOCX/期刊格式应当是 canonical draft 的可重建投影。** `slr-prisma` 展示了严格 Word 结构和图表嵌入；Pandoc 提供 Markdown/JSON/JATS/DOCX 多格式转换；本仓库已有 ACS-style `md2docx.py`。应保留 `review-content.md`/evidence-bound draft 为唯一内容源，并用 journal profile 驱动导出，不把 DOCX 当第二真相。[S9][S11][L6]

6. **`grill-with-docs` 的机制适合作为入口协议，不适合作为 Research 质量门。** Matt Pocock 的 `grilling` 是依赖感知的 frontier interview，`research` 是一次性产出、逐条引用的一手来源调查；其官方文档同时记录了研究任务嵌套导致重复运行、没有停止条件和旧研究文件不会自动复用等缺陷。这正好解释了我们要补“预算、去重、resume digest 和单代理边界”的原因。[S1][S2]

## 对比矩阵

| ID / 项目 | 研究入口与问题拆分 | 发现、全文、解析 | 证据/引用 | 图片/表格 | 人工确认、状态与迭代 | 输出 | 复用判断 |
|---|---|---|---|---|---|---|---|
| S1–S2 `mattpocock/skills` | `grilling` 以 design tree/frontier 分轮；`research` 将事实调查委托为单 Markdown 资产 | 不提供论文检索/全文管线 | 每条研究结论要求回到官方一手来源 | 无论文媒体管线 | frontier 结束后需确认；官方文档记录嵌套 sub-agent、无停止条件、旧文件不自动复用 | Markdown 研究笔记、CONTEXT/ADR（`grill-with-docs`） | **需适配**：直接吸收 frontier/source-discipline；补 Research 预算和 single-run guard |
| S3 STORM/Co-STORM | 观点/角色引导提问，模拟 writer–expert 对话；Co-STORM 支持用户插话 | 搜索引擎 retrievers；`VectorRM` 可接用户文档 | 生成带引用文章；答案必须基于检索信息 | 动态 mind map；无化学图像 provenance | STORM 两段式 pre-writing/writing；Co-STORM 的 discourse 可持续介入 | Wikipedia-like article、outline、conversation log、raw search results | **需适配**：用于 Grill+/Research coverage，不作为化学证据权威 |
| S4 PaperQA2 | 问题 → agentic search/gather evidence/answer；也支持手动添加文档 | 本地 PDF/TXT/Office/code 索引；Semantic Scholar/Crossref/Unpaywall 元数据；可复用 index | in-text citations、页码/文本 chunk；metadata-aware embedding、RCS；可调 `k`/`max_sources`/并发 | `ParsedMedia` 关联 chunk；PDF images/tables；read-time synthetic caption 只用于检索、不污染 source text | agent 或 fake（search→evidence→answer）路径；Settings 控制并发/来源数/解析器 | 答案、上下文、可缓存索引；不负责综述 DOCX | **需适配**：source ledger、page locator、媒体关联和 token budget 可借鉴；不能直接替代 claim-level chemical audit |
| S5 Open Deep Research | 可选 clarification；structured research brief；supervisor 委派 research units | Tavily/OpenAI/Anthropic/MCP；配置可选 API；网页内容压缩 | supervisor notes → compression → final report；有 structured-output retries | 无论文 figure/table 语义管线 | `max_concurrent_research_units`、最大迭代、tool calls、token/length 限制；legacy 有人类计划批准 | 可配置 research report；LangGraph/OAP UI | **需适配**：高层策略/并发/clarification；不得直接把网页报告当文献证据 |
| S6 GPT Researcher | planner 生成问题，execution agents 收集，publisher 聚合 | web + local documents；MCP retrievers；deep research tree、并行和 context management | source-track resource、报告引用；README 明确“实验性、as-is” | smart image scraping、AI inline image | frontend 实时进度和可配置 settings；无科学 claim gate | PDF、Word、Markdown 等报告 | **仅供参考/需适配**：并行和导出思路有用；化学来源身份、全文 locator、版权和科学审查缺失 |
| S7 `stephenlzc/AI-Powered-Literature-Review-Skills` | 8 阶段：Session Log → Query Analysis → Parallel Search → Dedup → Verification → Export → Paper Analysis → Citation Format → Synthesis 子阶段 | 浏览器访问多数据库，声称无需 API；元数据导出，单篇分析 | 基础 metadata verification、GB/T 7714 citation format；每 claim 引用要求写在 prompt | README/SKILL 未形成 figure inventory/provenance 契约 | Session 目录；Synthesis 内 Outline/Writing/Review/Final；每阶段输出文件 | Markdown references、analysis、review；可选 docx skill | **需适配**：阶段拆分和 session log 可借鉴；浏览器自动化和“基础验证”不足以支撑 Chemical GAP/claim readiness |
| S8 Aut_Sci_Write | 独立 `sci-search`/`sci-download`/`sci-extract`/`sci-figure`/`sci-review`/`sci-zotero` 等 | 多源 API + DOI routing；OA fallback；Paper Harvester full text + figures；degraded capture status | metadata merge/audit trail；`sci-review` 只含结构/语气 validator，未证明 claim-source entailment | Figure/Scheme/Chart/Supplementary 支持；hybrid/native/CV extraction、600 DPI、subfigure | 统一 `.env`；CLI；没有本项目式 canonical claim merge | Markdown raw/analysis、PPTX/HTML；review output | **需适配**：图片提取和 OA waterfall 可参考；AGPL `sci-figure` 与大量 API/版权边界需单独审查，不能直接复制实现 |
| S9 `research-paper-lifecycle-skills` | `paper-profile` + `literature-review`/`draft-survey`；`orchestrate-paper` goal→plan→execute→verify→reflect | key-free DBLP/Crossref/S2/arXiv；legal OA resolver；screening corpus；live venue/CFP | corpus single source of truth；BibTeX verification；claim anchors、forward-reference worklist；deterministic `check_review.py` gate | `polish-tables-figures`、figure/table crossref lint；非 PDF figure extractor | `paper-workspace/INDEX.md`、pipeline-state、human checkpoint；live reverify venue；不自动提交 | `review.md`、BibTeX、venue profile、preflight reports；可导出到 LaTeX/Overleaf | **需适配**：最值得吸收治理与可验证门；每阶段 sign-off 改成 acceptance/continuous 双模式 |
| S10 `slr-prisma` | 两到三轮 interview；可上传 protocol/search logs/data extraction | 依赖用户提供数据库、筛选、数据和计数；不是全文发现引擎 | PRISMA 2020 27-item checklist；APA 7 verification | PRISMA flow diagram；Word 中 table + standalone visual | 每 section 停下来等用户反馈；每个 selection count 明确确认 | strict journal `.docx`、flow diagram、checklist audit | **需适配/仅供参考**：作为未来 `systematic_review` profile；不应用于默认 narrative chemistry review |
| S11 `lingzhi227/agent-research-skills` | 31 skills；deep-research 6 phases：frontier→survey→deep dive→code→synthesis→report；survey-generation 多 LLM outline + RAG | Semantic Scholar/arXiv/OpenAlex/Crossref；目标 35–80 papers；Phase 3 强制读 ≥8 全文 | citation-management harvest/validate/dedupe；backward traceability；`paper_db.jsonl`/BibTeX | figure-generation/table-generation 独立技能；paper-assembly 传播状态 | 严格阶段文件门；每阶段增量保存；但含开发者机器绝对路径 | `report.md`/BibTeX、LaTeX、figures/tables、assembly checkpoint | **仅供参考**：覆盖面地图很有启发；固定 CS conference 与硬编码路径不适用于 Chemical Review |
| S12 Arcadia `agent-literature-review` | 多角色 AI lab、`/discuss` 多轮讨论；`/read_folder` 读本地论文 | arXiv/bioRxiv 搜索；本地 folder fallback | 讨论型摘要；没有 claim-level citation gate | 无正式图表 manifest | 用户可 @mention；显示 cost；原型级 | terminal conversation | **仅供参考**：可借鉴“本地 folder + 专家角色”；仓库自称 rough prototype，不能作为质量基线 |
| L1 本仓库当前 review-writing skills | discovery → matrix/outline → blueprint → section drafting → redraw → merge → final audit → DOCX | MinerU manifest/PDF + metadata registry；figure inventory | paragraph IDs、paper IDs、`[n]` callouts、citations.json、hard gate；central content source | figure candidates 按 paragraph anchor；source figure/redraw manifest；final audit 要求至少一图 | 多个明确 human checkpoints；`review-state`/orchestrator；尚未默认 continuous | first/final draft Markdown、ACS-style DOCX | **当前基线**：已有最强的图文绑定和化学审计接口；需补 discovery/evidence/claim readiness、批量执行和预算 |

## 项目卡片与可迁移结论

### S1–S2：Matt Pocock `grilling` / `research`

- `grilling` 明确要求把问题建成 design tree，每一轮一次性询问当前 frontier，事实由 agent 查而不是反问用户；官方说明“13 个问题约 3 轮”是预期形态。[S1]
- `research` 的交付物是单个带引用的 Markdown 文件，且只接受官方文档、源码、规范和一手 API 等 primary sources。[S2]
- 官方文档明确记录三个会直接影响 Chemical Review 的缺陷：research agent 可能再次调用 research 造成嵌套重复；skill 没有 stopping criterion；旧研究文件不会自动进入后续上下文。[S2]
- **决策**：吸收 frontier interview、研究资产单文件和 primary-source discipline；为 Chemical Review 增加 `run_id`/`parent_agent` 防嵌套、query/paper/token/time budget、digest-based resume、coverage stopping rule。不要把该 skill 当作全文或引用验证器。

### S3：STORM / Co-STORM

- STORM 把长文生成拆为 pre-writing（检索、引用、outline）和 writing（基于资料写作）两步，并用 perspective-guided questions + simulated writer/expert conversation 增强问题覆盖。[S3]
- Co-STORM 将专家 agent、moderator 和 human user 组织为协作 discourse，并维护动态 mind map 来降低长对话的认知负担。[S3]
- `VectorRM` 支持用户提供文档，这一点比只依赖公开网页更接近我们的“主题 + 授权 PDF 文件夹”入口。[S3]
- **决策**：为 Grill+ 增加“用户目标/背景/先验/争议/证据标准”问题簇，为 Research 增加多视角 coverage map；不采用 STORM 的 Wikipedia-style source semantics 作为化学 claim authority。

### S4：PaperQA2

- PaperQA2 的核心路径是 local corpus indexing + metadata-aware retrieval + agentic evidence gathering + grounded answer，并明确支持 Semantic Scholar、Crossref、Unpaywall 的冗余 metadata fetching。[S4]
- `Docs` 同时接受 PDF、文本、Office 和代码；索引可复用，manifest 可预先提供 DOI/title/file location，减少 LLM 元数据猜测。[S4]
- PDF media 以 `ParsedMedia` 对象和 text chunks 建立关联；图片/表格可以在读取阶段生成 synthetic caption 以帮助检索，但 caption 与原文保持分离，避免伪造 source text。[S4]
- `answer_max_sources`、`max_concurrent_requests`、`evidence_k` 等设置说明了一个可操作的 token/并发预算接口。[S4]
- **决策**：source registry 增加 `paper_manifest`、`page/chunk locator`、`media_id` 和 `retrieval_budget`；媒体 caption 只能作为检索辅助，正文事实仍必须绑定原始 PDF locator。

### S5：Open Deep Research

- 配置中公开暴露 `allow_clarification`、最大并发 research units、最大 supervisor iterations、最大 tool calls、最大 content length 和三类模型（summarization/research/compression/final report）。[S5]
- 主流程先判断是否需要 clarification，再生成 structured research brief，supervisor 以 `ConductResearch`/`ResearchComplete`/`think_tool` 管理研究分支。[S5]
- 仓库 README 还保留了“Plan-and-Execute + human-in-the-loop planning”和“supervisor + parallel processing”的 legacy 对照，说明同一产品可以把交互确认和连续执行作为可切换策略。[S5]
- **决策**：借鉴其高层 Research Policy（速度/隐私/完整性）到 adapter 编排，不暴露底层开关；用预算和 structured state 把“连续执行”变成有限循环。

### S6：GPT Researcher

- README 的 planner→execution→publisher 结构将“问题生成、资源收集、source tracking、聚合写作”分开，并支持 web/local documents/MCP。[S6]
- 该项目声明支持图片抓取/过滤、PDF/Word/Markdown 导出、递归 deep research、并行处理和 context management。[S6]
- README 同时声明项目是 experimental、as-is，并明确“不应把它当成学术建议或论文推荐”。[S6]
- **决策**：只吸收并行 planner/executor/publisher、progress UI 和 export seam；不吸收“多网页频率降低错误”作为 Chemical Review 的科学验证策略，必须由 DOI/PDF/locator/claim gate 替代。

### S7：`AI-Powered-Literature-Review-Skills`

- 该 skill 的 8 阶段覆盖 Session Log、关键词分析、并行浏览器检索、去重、基础验证、数据导出、单篇分析、引用格式和 synthesis 子阶段；Synthesis 还拆为 Outline/Writing/Review/Final。[S7]
- 输出契约包括 `metadata.json`、`papers_raw.json`、`references.md`、`papers_analysis.md`、`review_report.md`、`literature_review.md` 等阶段文件，并可选 docx skill。[S7]
- 其配置优先浏览器自动化、避免 API key；这降低首次配置，但检索结果/全文/定位是否可靠取决于页面行为，不能替代化学 evidence readiness。[S7]
- **决策**：借鉴 session log、phase artifacts 和最终 review 子阶段；将“基础 metadata verification”升级为 `DISCOVERY_READY → EVIDENCE_READY → CLAIM_READY`，并加入 source hash、locator 和失败原因。

### S8：Aut_Sci_Write

- `sci-search` 同时列出 Web of Science、Elsevier、Springer、Semantic Scholar、OpenAlex、PubMed、Europe PMC、Crossref、Unpaywall、IEEE、arXiv、Zotero 等来源；`sci-download` 以 DOI 前缀路由并做 OA waterfall。[S8]
- `sci-extract` 的 Paper Harvester 生成带全文和图片的 `raw.md`，保留 metadata audit trail，并声明在无 publisher figure 时从 PDF crop。[S8]
- `sci-figure` 代码/skill 明确支持 Figure/Scheme/Chart/补充图、subfigure label、native/CV/caption fallback、600 DPI 和 `caption_text/page/bbox/engine_used` 等字段。[S8]
- `sci-review` 自带 validator，但其代码仅检查所需标题和禁用短语，不等于 claim-source entailment 或化学真实性验证。[S8]
- **决策**：可参考 OA waterfall、figure inventory 字段和 extraction fallback；必须先做许可/依赖审查（`sci-figure` 是 AGPL-3.0-or-later），并把提取状态与本项目 source registry 对齐。[S8]

### S9：`research-paper-lifecycle-skills`

- `literature-review` 维护 screening corpus、criteria、theme、claim anchors 和 synthesis matrix；搜索、全文获取、引用验证分给 sibling skills，避免在 orchestrator 中重写 adapter。[S9]
- 它把 `corpus.json` 作为 cite key 的 single source of truth，要求验证报告有 provenance，PARTIAL-PASS/FAIL 不能被标成 verified，并用 `check_review.py` 阻断未知/未验证/排除的引用。[S9]
- `orchestrate-paper` 的 goal→plan→execute→verify→reflect→checkpoint loop 以 compile、DOI resolve、lint、page count 等外部信号验收，且明确永不提交/发布。[S9]
- `add-venue-profile` 要从本年度官方 CFP 建 profile，保留 verified URL/date/confidence；`preflight-check` 会检查模板、页数、匿名化和必需章节。[S9]
- **决策**：这是最适合借鉴的治理层：source registry/corpus、外部验证信号、live journal profile、durable state 和 reflect log。要把“每阶段 author sign-off”做成 acceptance 模式；continuous 模式只在硬阻塞暂停。

### S10：`slr-prisma`

- Phase 1 先从用户文件中抽取 protocol、搜索日志、筛选表和参考文献，缺什么才询问；访谈覆盖数据库、日期、检索式、纳入/排除、screening、risk of bias、synthesis 和计数。[S10]
- Phase 2 按 PRISMA 27 项映射完整期刊结构；Phase 3 生成带注释的 PRISMA flow diagram；Phase 5 输出 strict journal `.docx`，Phase 6 可审计 checklist。[S10]
- 该 skill 强制 APA 7，并且每节后暂停等用户反馈；它是 systematic review 报告规范，不是叙事型化学 review 的默认模板。[S10]
- **决策**：未来增加 `systematic_review` profile 时复用 protocol/eligibility/flow-count/checklist；当前 Chemical Review 只复用“先读用户已有资料、缺口定向追问、图表与 docx 共同生成”。

### S11：`agent-research-skills`

- `deep-research` 强制 6 phase 文件门，要求 Phase 2 形成 35–80 paper DB、Phase 3 读至少 8 篇全文、Phase 4 调查至少 3 个代码仓库，才进入 synthesis/report。[S11]
- `survey-generation` 使用多份 outline 合并、RAG subsection writing、citation validation 和 local coherence；`citation-management` 有 BibTeX validate/harvest/dedupe；`paper-assembly` 传播阶段状态并验证图片/引用/编译。[S11]
- 该仓库明确包含开发者绝对路径和 AI/CS conference 优先级，不能作为 Chemical Review 的现成执行器。[S11]
- **决策**：只借鉴“深读门、代码/工具生态支线、citation/figure/table 独立 skill、assembly checkpoint”的分层，不采用固定论文数量或学科排序。

### S12：Arcadia Agent Literature Review

- 该项目是 terminal-based AI laboratory rough prototype：角色化多 agent、@mention、`/discuss` 多轮讨论、arXiv/bioRxiv search、`/read_folder` 本地论文、`/cost` 费用查看。[S12]
- README 明确称 bioRxiv API 不稳定，因此加入 local-folder fallback；这与我们将用户授权 PDF 作为优先输入的方向一致。[S12]
- **决策**：只参考“本地文件夹 + 多角色讨论 + cost visibility”；不引用其对科学质量的暗示，也不把它当作完成的 review pipeline。

## 与当前 Chemical Review 的差距映射

当前本仓库已有：

- `chemical-review` 的单一 orchestrator seam、`workflow-state.md`、`review-intent.md`、`domain-profile.md` 和明确 human boundary。[L1]
- `review-writing-orchestrator` 的 discovery → matrix/outline → blueprint → section drafting → figure redraw → merge → final audit → DOCX 资产链，以及 hard gates（至少一图、citation callouts、References、图片路径、source placeholder）。[L1][L4][L5][L6]
- `review-section-drafting-figure-picking` 的 paragraph ID、paper ID、figure candidate ID 和 source figure inventory；这比多数外部项目更接近 claim/figure 级合并。[L4]

尚缺或应重新定义：

| 差距 | 外部证据启发 | Chemical Review 的最小迭代 |
|---|---|---|
| Grill 只像六字段 intake | S1–S3、S5、S10 | 多轮 frontier + 用户已有文档抽取；把目的/背景/先验/科学变量/证据标准/停止条件放入可持久化 intent；非相关隐私不收集 |
| metadata 被误解为 Research 完成 | S4、S7、S9 | source registry 状态 `DISCOVERY_READY`、`EVIDENCE_READY`、`CLAIM_READY`；状态投影展示 readiness，不只展示 phase |
| 搜索路线缺少预算/饱和 | S1–S2、S4、S5、S11 | query/paper/full-text/token/time budget；bounded 以 coverage matrix + marginal gain 停止；失败和 PARTIAL 必须可见 |
| 全文/解析/图片分散 | S4、S8、G1、G2 | `paper_manifest` + `parse_manifest` + `figure_inventory`；每个 Figure/Scheme/Table 有 locator、caption、hash、resolution、target section、source status |
| 人工确认过多 | S5、S9、S10、L1 | `acceptance` 保留 stage gates；`continuous` 批量执行 ready units，仅硬阻塞/HUMAN_ACTION_REQUIRED 暂停 |
| claim blocks 未进入中央内容源 | S4、S9、L1 | DOI/URL parser 回归测试；central `review-content.md` 只接受 `CLAIM_READY` block；Markdown/DOCX/source digest 一致性门 |
| 文献比较维度不结构化 | S9、S10、S11、L1 | matrix 必须有 conditions/units/endpoints/comparability；化学不确定性显式 `UNKNOWN`/`NOT_COMPARABLE`/`Chemical GAP` |
| 目标期刊格式没有 profile | S9、S10、L6、G3 | generic chemistry profile + 用户指定的 live journal profile；未指定期刊保持 `NOT_SELECTED`；导出前保存官方指南快照和 digest |
| token/成本不可见 | S4、S5、S6、S12 | `run_budget.json`、阶段 token/请求/并发计数、缓存命中和 retry；前台只显示摘要，完整 ledger 留在项目资产 |

## 迭代优先级（讨论结论，不是实施授权）

### P0：契约和状态

1. 运行模式 `continuous` / `acceptance`；首次运行询问，项目级持久化。
2. Grill+ frontier interview，支持从上传的 proposal/search log/PDF manifest 提取已知信息，只问缺口。
3. `DISCOVERY_READY` / `EVIDENCE_READY` / `CLAIM_READY` 三层 readiness，禁止 metadata 自动升级为正文事实。
4. source registry、DOI/URL canonicalization、PDF hash、parser status、locator 和 figure inventory 统一身份。
5. central claim merge 与 `review-content.md` 的真实写入，修复 evidence-ID `https` 截断回归。

### P1：Research 最优路线

1. 多源发现（OpenAlex/Semantic Scholar/Crossref 等）+ 去重 + coverage matrix；用户 PDF 与公开 OA 合并。
2. 高层 Research Policy：速度优先、隐私优先、完整性优先；底层 adapter 自动选路。
3. API/本地工具探测；无 key fallback；用户选择推荐路线时生成可执行 setup wizard，不自动修改 auth/shell/.env。
4. 本地/云端解析授权、MinerU/GROBID/Docling fallback、parse quality gate；云端上传前项目级确认。
5. bounded stopping rule：路径覆盖 + 连续无新增重要方向 + 未覆盖区清单；所有 PARTIAL/失败写入 ledger。

### P2：图表和综述结构

1. Research 生成 Figure/Scheme/Table inventory；PRD 生成 section-to-asset placement plan。
2. 初版只允许原图裁剪/缩放/重排/有限标注；保留 caption、DOI/Figure/page locator 和 source hash。
3. section paragraph ↔ claim ↔ figure candidate ↔ citation 绑定；review 阶段做图文一致性检查。
4. 未来的 adapted/redrawn figure 单独标记，要求人工比对；不能把模型重绘当原图。

### P3：导出和期刊 profile

1. generic chemistry DOCX 先稳定，Markdown/source digest 作为唯一内容权威。
2. 用户指定期刊后，从官方 author instructions/CFP 生成版本化 profile；未指定保持 `NOT_SELECTED`。
3. DOCX 与 Markdown digest 冲突时暂停，不静默覆盖；保留可重建 manifest。
4. 导出后运行 heading/reference/figure/table/math/layout QA；DOCX 仅代表排版结果，不代表科学接受。

## 不应直接照搬的做法

- 只用网页 snippet/元数据写综述：会重现本次 `metadata-only` 缺陷；必须有全文/locator 或明确降级。
- 固定“必须 35–80 篇”或“必须 70 篇”：数量不是化学综述的停止条件，应由 coverage/comparability/边际新增价值决定。[S9][S11]
- 把每阶段人工 sign-off 永久设为默认：适合 acceptance，不适合正常连续执行。[S5][S9][S10]
- 将 AI 生成图片或网页图片混入证据正文：源论文图、caption、locator、hash 与 adapted/redrawn 状态必须分开。[S3][S4][S8][L4]
- 只做标题/禁用短语 validator 就宣布科学质量通过：Aut_Sci_Write 的 `sci-review` validator 仅是轻量结构检查。[S8]
- 直接复制带绝对本机路径、特定数据库、特定学科优先级的 workflow：必须先抽象成 Chemical Review 的 project-root、authorized-PDF-folder 和 policy profile。[S7][S11]
- 把 DOCX 当可回写数据库：DOCX 修改与 canonical Markdown 不一致时应检测冲突并停下。[S9][L6]

## 未覆盖项与下一轮需要验证的事实

1. 本调查没有运行各外部项目的真实检索、PDF 解析、figure extraction 或 DOCX export；性能、召回率、引用精度和 token 成本均不能从 README 直接确认。
2. 没有核验各项目依赖的数据库许可、publisher API 条款、PDF 再分发条件或模型服务的数据处理政策；真正接入前必须做单独的 source/licence review。
3. 尚未比较各 PDF parser 在化学双栏、反应 Scheme、结构式、表格跨页和补充信息上的真实质量；应以本项目的 5–10 篇 nickel-coupling fixture 做对照。
4. 尚未选择目标期刊，因此 generic chemistry profile 只能先验证“可重建”和“图文/引用顺序正确”，不能声称满足某个期刊的实时要求。
5. 外部项目的 README/SKILL 可能随时间变化；本报告记录了调查时的 default branch commit，真正采用前仍应重新读取当前官方文件。

## 原始来源清单

以下链接均指向调查时读取的官方仓库文件或本地 skill 文件；`commit` 用于固定当时版本。

| ID | 官方来源（固定 commit） | 读取定位 |
|---|---|---|
| S1 | [mattpocock/skills `grilling.md`](https://github.com/mattpocock/skills/blob/5b15a47f2d7150f545fbcacbfe381787fc0230dc/docs/productivity/grilling.md) | `What it does`; `round/frontier`; `facts vs decisions`; `It's working if` |
| S2 | [mattpocock/skills `research.md`](https://github.com/mattpocock/skills/blob/5b15a47f2d7150f545fbcacbfe381787fc0230dc/docs/engineering/research.md) | `What it does`; `Delegated legwork`; `Common questions`; nesting/no stopping criterion/reuse |
| S3 | [stanford-oval/storm `README.md`](https://github.com/stanford-oval/storm/blob/fb951af7744dab086e34962e9bc6fe878e145f83/README.md) | `How STORM & Co-STORM works`; `VectorRM`; `API`; runner stages |
| S4 | [Future-House/paper-qa `README.md`](https://github.com/Future-House/paper-qa/blob/57e89f7223b0960d5ee5ea048c69e3c47e088572/README.md) | `What is PaperQA2`; `Agentic Adding/Querying Documents`; `Multimodal Support`; `Manifest Files`; `Settings Cheatsheet` |
| S5 | [langchain-ai/open_deep_research `README.md`](https://github.com/langchain-ai/open_deep_research/blob/1b7d2e80db9faa586165c60e09096dbbfd483a64/README.md) + [`configuration.py`](https://github.com/langchain-ai/open_deep_research/blob/1b7d2e80db9faa586165c60e09096dbbfd483a64/src/open_deep_research/configuration.py) + [`deep_researcher.py`](https://github.com/langchain-ai/open_deep_research/blob/1b7d2e80db9faa586165c60e09096dbbfd483a64/src/open_deep_research/deep_researcher.py) | configurable models/search, concurrency/iterations, clarification, supervisor/brief |
| S6 | [assafelovic/gpt-researcher `README.md`](https://github.com/assafelovic/gpt-researcher/blob/e54c49639814191591a0b26973fa9c58532c4ba3/README.md) | `Architecture`; `Features`; `Deep Research`; `Research on Local Documents`; `Export`; experimental disclaimer |
| S7 | [stephenlzc/AI-Powered-Literature-Review-Skills `README.md`](https://github.com/stephenlzc/AI-Powered-Literature-Review-Skills/blob/ba295ed837ee9b7b537243acd702846bca035807/README.md) + [`SKILL.md`](https://github.com/stephenlzc/AI-Powered-Literature-Review-Skills/blob/ba295ed837ee9b7b537243acd702846bca035807/SKILL.md) | 8-stage workflow, output files, citation/review phases, browser DB access |
| S8 | [ShZhao27208/Aut_Sci_Write `README.md`](https://github.com/ShZhao27208/Aut_Sci_Write/blob/357766f90bd42f4f982d054be55c687c27202f22/README.md), [`sci-review/SKILL.md`](https://github.com/ShZhao27208/Aut_Sci_Write/blob/357766f90bd42f4f982d054be55c687c27202f22/skills/sci-review/SKILL.md), [`sci-figure/SKILL.md`](https://github.com/ShZhao27208/Aut_Sci_Write/blob/357766f90bd42f4f982d054be55c687c27202f22/skills/sci-figure/SKILL.md), [`sci-extract/SKILL.md`](https://github.com/ShZhao27208/Aut_Sci_Write/blob/357766f90bd42f4f982d054be55c687c27202f22/skills/sci-extract/SKILL.md) | API matrix, DOI routing, Paper Harvester, figure fields/engines, lightweight validator |
| S9 | [ShaishavMaisuria/research-paper-lifecycle-skills `README.md`](https://github.com/ShaishavMaisuria/research-paper-lifecycle-skills/blob/f9a0ed8f0f1770fb0321c5b022d55ed34c939927/README.md), [`literature-review/SKILL.md`](https://github.com/ShaishavMaisuria/research-paper-lifecycle-skills/blob/f9a0ed8f0f1770fb0321c5b022d55ed34c939927/skills/literature-review/SKILL.md), [`draft-survey/SKILL.md`](https://github.com/ShaishavMaisuria/research-paper-lifecycle-skills/blob/f9a0ed8f0f1770fb0321c5b022d55ed34c939927/skills/draft-survey/SKILL.md), [`orchestrate-paper/SKILL.md`](https://github.com/ShaishavMaisuria/research-paper-lifecycle-skills/blob/f9a0ed8f0f1770fb0321c5b022d55ed34c939927/skills/orchestrate-paper/SKILL.md) | corpus/claim gate, legal OA, goal-plan-verify-reflect, live venue profile |
| S10 | [keemanxp/slr-prisma `README.md`](https://github.com/keemanxp/slr-prisma/blob/0614d2f6d39f5d31d0ae63fdff39f9553c90449c/README.md) + [`SKILL.md`](https://github.com/keemanxp/slr-prisma/blob/0614d2f6d39f5d31d0ae63fdff39f9553c90449c/SKILL.md) | interview, PRISMA phases, Word/flow diagram/checklist, APA verification |
| S11 | [lingzhi227/agent-research-skills `README.md`](https://github.com/lingzhi227/agent-research-skills/blob/9e6c085d65e313e475e921fdfe795ac11eb7589e/README.md), [`deep-research/SKILL.md`](https://github.com/lingzhi227/agent-research-skills/blob/9e6c085d65e313e475e921fdfe795ac11eb7589e/skills/deep-research/SKILL.md), [`survey-generation/SKILL.md`](https://github.com/lingzhi227/agent-research-skills/blob/9e6c085d65e313e475e921fdfe795ac11eb7589e/skills/survey-generation/SKILL.md), [`citation-management/SKILL.md`](https://github.com/lingzhi227/agent-research-skills/blob/9e6c085d65e313e475e921fdfe795ac11eb7589e/skills/citation-management/SKILL.md), [`paper-assembly/SKILL.md`](https://github.com/lingzhi227/agent-research-skills/blob/9e6c085d65e313e475e921fdfe795ac11eb7589e/skills/paper-assembly/SKILL.md) | phase gates, deep read/code survey, RAG/citation/figure/table/assembly skills |
| S12 | [Arcadia-Science/agent-literature-review `README.md`](https://github.com/Arcadia-Science/agent-literature-review/blob/c007798243473c74e01a595d08d352b5609feea6/README.md) | local folder fallback, multi-agent discussion, cost command, rough-prototype notice |
| G1 | [opendatalab/MinerU `README.md`](https://github.com/opendatalab/MinerU/blob/4fe4bde114a23ee5dd637eae99b767f4669bf58c/README.md) | structured Markdown/JSON, images/tables/formulas, OCR, local/API/CLI |
| G2 | [grobidOrg/grobid `Readme.md`](https://github.com/grobidOrg/grobid/blob/0b0ab53b159b32792a01fca1d9d04fd02cf8b24b/Readme.md) | PDF→TEI, bibliographic/reference parsing, citation contexts, figures/tables, coordinates |
| G3 | [jgm/pandoc `README.md`](https://github.com/jgm/pandoc/blob/1c81441a7ac2715ac41d3867cd9a36d6a459bcb3/README.md) | Markdown/JSON/JATS/DOCX formats, citations, math, conversion limits |
| L1 | [`chemical-review/SKILL.md`](/home/kenqia/my_folder/review-writer-skill/.agents/skills/chemical-review/SKILL.md) and [`review-writing-orchestrator/SKILL.md`](/mnt/c/Users/26960/.codex/skills/review-writing-orchestrator/SKILL.md) | current project seam/state/human boundary and review pipeline |
| L4 | [`review-section-drafting-figure-picking/SKILL.md`](/mnt/c/Users/26960/.codex/skills/review-section-drafting-figure-picking/SKILL.md) | paragraph/paper/figure anchors, inventory, citation callouts |
| L5 | [`review-final-audit-release/SKILL.md`](/mnt/c/Users/26960/.codex/skills/review-final-audit-release/SKILL.md) | figure/citation/reference hard gates and source placeholder checks |
| L6 | [`review-export-docx/SKILL.md`](/mnt/c/Users/26960/.codex/skills/review-export-docx/SKILL.md) | canonical Markdown→ACS-style DOCX mapping and image resolution |
