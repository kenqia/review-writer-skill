# Chemical-review Research 工具核对

v2 的 canonical Research 接口与用户路线在以下文件中：

- [`../../.agents/skills/chemical-review-research/SKILL.md`](../../.agents/skills/chemical-review-research/SKILL.md)
- [`../../.agents/skills/chemical-review-research/research.py`](../../.agents/skills/chemical-review-research/research.py)

正式 adapters 为 OpenAlex、Semantic Scholar、Crossref、PubChem、ChEBI、Unpaywall、Europe PMC、CORE 与 MinerU。MinerU 是主解析器，`pdftotext` 是本地低保真 fallback；v1 的 GROBID/Docling 推荐列表已 superseded。
