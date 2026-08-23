# Chemical-review Research 工具核对

核对日期：2026-08-23。本文只记录公开的一方文档所定义的职责边界；工具不可用时，Research 阶段应降级为人工提供的 DOI/URL/PDF、浏览器检索或已有本地文献，并明确记录未覆盖范围。工具命中或解析成功不等于科学结论已被验证。

## 工具边界

| 工具 | Research 阶段适合做什么 | 不应承担的职责 | 可降级路线 |
|---|---|---|---|
| [OpenAlex](https://docs.openalex.org/) | 开放学术作品、作者、机构、期刊和主题的发现、筛选与元数据补全；适合扩展检索集合。 | 不是全文事实库，也不证明某个化学断言或文献质量。 | Crossref、Semantic Scholar、用户 DOI/题录；人工核对原文。 |
| [Semantic Scholar API](https://api.semanticscholar.org/api-docs/) | 论文搜索、引用/被引关系、作者和摘要等发现信号；适合找相关工作和引用网络。 | 摘要/排名不能代替全文，也不能当作实验数据来源。 | OpenAlex、Crossref、Europe PMC；人工检索。 |
| [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | DOI 注册元数据、题名、作者、期刊、年份及参考文献等书目信息。 | 注册元数据不等于全文、开放获取或事实真实性。 | OpenAlex、Semantic Scholar、出版社页面；用户提供 DOI。 |
| [PubChem PUG-REST](https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest-tutorial) | 化合物/物质标识、名称、结构、同义词和可查询属性的机器访问；用于身份核对和术语对齐。 | 不是对某篇论文实验条件、产率或机理的证明；结构映射仍需人工检查。 | ChEBI、论文 SI/原文、用户确认；保留 Chemical GAP。 |
| [ChEBI](https://www.ebi.ac.uk/chebi/aboutChebiForward.do) | 由 EMBL-EBI 维护的化学实体及本体分类/定义，用于术语、实体和层级对齐。 | 本体定义不能替代论文中的操作性定义、样品状态或反应证据。 | PubChem、IUPAC/权威教材、原始论文。 |
| [Unpaywall API](https://unpaywall.org/products/api) | 依据 DOI 查找合法开放获取位置和版本线索，辅助取得全文。 | 不保证全文存在、可下载、版本等同或内容质量。 | Europe PMC、CORE、出版社开放页面、用户上传的授权 PDF。 |
| [Europe PMC RESTful API](https://europepmc.org/RestfulWebService) | 生物医学/生命科学论文与全文的检索、元数据和开放全文访问；化学生物学主题尤其有用。 | 覆盖范围不是全部化学；索引记录和全文都不自动证明化学结论。 | OpenAlex、Crossref、出版社、机构仓储。 |
| [CORE API](https://api.core.ac.uk/docs/v3) | 聚合开放获取论文/全文记录，补充机构仓储和开放全文发现。 | 聚合记录可能缺页、版本差异或解析质量问题；不替代原始出版物。 | Unpaywall、Europe PMC、出版社/机构仓储、人工获取。 |
| [MinerU](https://opendatalab.github.io/MinerU/) | 将 PDF 等文档解析为结构化内容，尽量保留版面、表格、公式、图片和文本，供后续阅读与定位。 | 解析器不是来源；解析错误不能被当成论文事实，图表/公式需回看 PDF。 | GROBID、Docling、纯文本/OCR、人工阅读原 PDF。 |
| [GROBID](https://grobid.readthedocs.io/en/latest/) | 基于机器学习的科学文献结构化解析，尤其是 TEI/XML、标题、作者、正文和参考文献。 | 不保证复杂版面、化学结构、表格和公式无误；不负责科学解释。 | MinerU、Docling、PDF 原文与人工定位。 |
| [Docling](https://docling-project.github.io/docling/) | 文档转换与结构化表示，支持 PDF 等多种格式，适合作为通用解析后端。 | 转换结果仍是中间产物，不是事实验证或引用裁决。 | MinerU、GROBID、OCR、人工复核。 |

## 推荐路线与降级原则

1. 先用 OpenAlex + Semantic Scholar + Crossref 扩展和去重题录；以 DOI/出版社记录作为身份核对锚点。
2. 用 PubChem + ChEBI 做化学实体与术语辅助核对；定义、结构、性质和实验事实必须分开处理。
3. 用 Unpaywall，再用 Europe PMC/CORE 和出版社或机构仓储寻找合法全文；没有全文时保留为待补证据，不用摘要补写实验细节。
4. 解析优先 MinerU；按文献类型和失败表现切换 GROBID 或 Docling。任何解析器输出都要保留 PDF 页码/章节定位，并对表格、公式、结构图和 SI 做人工复核。
5. 全部外部服务不可用时仍可用用户提供的 DOI、题录和 PDF 完成受限 Research；结果标注覆盖边界，允许后续迭代补检索。

## 当前内置路线

仓库当前内置 `research.OpenAlexDiscoveryAdapter`，默认由 orchestrator 的
`run_research()` 通过 `ResearchConfig.default()` 启用，用于真实的 OpenAlex Works 搜索。
它只负责发现和元数据整理，不把摘要或排名当作化学事实；HTTP、JSON、限流和不可用情况会
进入 Research 的工具降级记录。其余发现、实体、全文和解析能力仍通过可替换 adapter 注入。

可选环境配置为 `OPENALEX_API_KEY` 和 `OPENALEX_MAILTO`。配置值只用于请求，不写入 Markdown
资产、错误消息或日志；没有配置时仍尝试公开端点，失败则保留 `HUMAN_ACTION_REQUIRED`/降级路线。
搜索参数和响应字段依据 [OpenAlex API searching](https://help.openalex.org/api/searching/)；
实施时仍应记录实际请求日期、端点和服务返回版本/字段。

Adapter 只能声明 `OPEN_ACCESS`、`USER_AUTHORIZED` 或 `INSTITUTION_AUTHORIZED` 三种全文访问依据，并同时返回来源 locator；该声明是可审阅的配置契约，不是平台对版权状态的独立法律裁决。解析输出还需给出 PDF 页码或章节 locator，否则仅保留元数据并记录解析降级。

## 适用前提与版本记录

- 本核对基于上述官方文档入口在 2026-08-23 的公开说明；未锁定 API 版本，实施时应记录实际请求日期、端点和服务返回版本/字段。
- 2026-08-23 使用不经本机代理的只读 HTTP 请求复核了上述 11 个官方入口，均返回 HTTP 200；这只证明文档入口当时可访问，不证明具体 API、凭据、配额或本地解析器当前可用。
- API 速率限制、认证要求、许可和全文访问权限应在用户配置阶段单独确认；不得把凭据写入项目或研究产物。
