# Framework 材料接入与比较主轴

本页定义 Framework 如何把 Research 材料变成可比较的证据表示。它不替代 Research 的 discovery、全文获取、解析或原始 PDF 核验。

## 先固定材料范围

在 `evidence-matrix.md` 开头写清：confirmed brief 版本或确认日期、Research handoff 版本、纳入的文献/研究集合、MinerU 或其它解析材料范围、用户额外 allowlist，以及本轮没有读取的材料。若 brief 仍是草案、候选集尚未接受、关键 stable identity/source identity（稳定身份/来源 identity）不稳定或 locator 缺失，先标记边界并决定是继续做局部框架还是 return to Research（返回 Research）。每条证据还必须提供 auditable locator（可审计定位）。

同一份解析文本可以是可信来源表示，也可以承载作者的解释。每一项重要观察都要有 auditable locator（可审计定位）。两者必须分开：

- `TRUSTED_SOURCE_TEXT`：trusted source text（来源 identity 正确、locator 可追溯的 MinerU 文本、表格或图注表示）；
- `SOURCE_OBSERVATION` / `SOURCE_FACT`：来源在明确 locator 直接报告的观察或事实；
- `AUTHOR_HYPOTHESIS`：原作者提出的机制、因果或解释假说；
- `MODEL_SYNTHESIS`：Framework 跨来源比较、归纳或解释；
- `MODEL_HYPOTHESIS`：尚待实验或文献检验的模型推断；
- `VERIFIED_SOURCE_FACT`：对原始 PDF 额外核对后的来源事实，不是使用 MinerU 的前置门槛；
- `UNKNOWN`：材料没有给出或当前无法可靠确定；
- `NOT_COMPARABLE`：比较所需的终点、条件、对照或口径不一致；
- `Chemical GAP`：当前证据范围无法回答的化学问题。

“可信解析”只说明来源表示忠实；it does not prove 作者机制、跨论文因果关系或模型综合正确。不要因为 `SOURCE_EXCERPT` 这个工作标签或 parser-excerpt gate 的旧习惯就阻止证据整理，也不要把 excerpt 自动升级为来源事实。

## 通用比较主轴

用 brief 相关的字段填充以下主轴；不适用的字段可以写 `N/A` 并说明原因，不能为了填表臆造数值。

| 比较字段 | 必须说明的问题 |
| --- | --- |
| 研究对象/体系（system） | 研究了什么分子、材料、方法、环境、模型或生物系统？身份、组成、状态和边界是什么？ |
| 变量/干预（variable/intervention） | 改变了什么，哪些因素保持不变，变量是否真正可归因？ |
| 实验或计算情境（context） | 条件、尺度、时间、温度、溶剂、仪器、模型、训练/测试划分或其它上下文是什么？ |
| 对照（comparator） | 与什么基线、空白、传统方法、未处理体系或替代计算比较？ |
| 终点（endpoint） | 测量了什么结果，单位、分母、误差、检测窗口和统计口径是什么？ |
| 观察结果 | 来源直接报告了什么，数值或趋势位于哪个 locator？ |
| 证据定位 | identity、版本、page/section/table/figure/equivalent locator 是什么？ |
| 限制（limitation） | 来源自身或本次提取有哪些限制、缺失和潜在偏差？ |
| 混杂因素（confounder） | 哪些未控制因素也能解释结果差异？ |
| 适用边界 | 该观察可以推广到哪里，在哪些条件下不能推广？ |

比较主轴是最小共同语言，不是固定数据库 schema。涉及有机反应时可以加入底物类别、催化剂状态、配体、选择性、产率、动力学和机制探针；材料主题可以加入组成、加工历史、形貌、测试协议、衰减和器件情境；分析主题可以加入基质、校准、检出限、选择性、回收率和验证设计；药化、化学生物学、物化、环境或计算主题按 brief 生成其它字段。任何领域模块都必须说明为什么该字段改变当前判断。

## Evidence matrix 的写法

每一行代表一个可被比较的研究、研究子集或明确的缺口，不强迫一篇论文只有一行。对同一研究有多个终点时拆行并保留分母/测量口径；对同一终点有多个条件时拆行并保留条件差异。矩阵至少让读者看到：

1. 这一行的来源与观察是什么；
2. 哪些字段可与其它行比较，哪些字段导致 `NOT_COMPARABLE`；
3. 这项证据支持、削弱或限定了哪一个 core claim；
4. 哪个是来源陈述，哪个是作者解释，哪个是 Framework 综合；
5. 下一步是补 Research 证据、改变比较分组，还是可以进入判断框架。

不要把摘要、metadata、引用次数或 parser 成功消息当作完整行。缺失值写 `UNKNOWN`，跨研究不能合法对齐的终点写 `NOT_COMPARABLE`，当前范围无法回答的核心问题写 `Chemical GAP`。
