# DOCX 投影与交付边界

DOCX 是 `journal-manuscript.md` 的一次性 projection。使用宿主已有的文档生成能力即可；Publication skill 本身不引入 provider、转换脚本或隐藏数据层，也 does not mutate canonical source。

## 生成与一致性

先完成并检查 Markdown projection，再从同一版本生成 `journal-manuscript.docx`。DOCX 应保留主要标题层级、摘要、正文、表格、图题、引用和参考文献的语义顺序；它可以有期刊所需的页眉、页脚、字体和分页，但不得改变科学文本。

至少检查：

- 文件确实是可打开的 Word 文档，而不是只有扩展名；
- 标题、章节、表格、caption、citation 和 references 没有丢失或错位；
- 内部 MinerU/parser、附件、QA routing、Evidence ID 和 stage/unit 元数据没有进入读者稿；
- `UNKNOWN`、`NOT_COMPARABLE`、Chemical GAP、限制和模型假设仍以自然语言存在；
- source-linked visuals 的来源、caption、locator、citation 关系仍然清楚；
- DOCX 与 Markdown 的重要 claim、语气和范围一致。

如果宿主当前不能生成 DOCX，明确报告能力缺口与需要的用户动作，交付已完成的 Markdown projection；不要用一段伪造的成功消息替代文件，也不要把新脚本变成科学流程依赖。

## 时序与权威

Publication 可以在 QA 前或 QA 后调用。pre-QA 的文件称为“journalized draft（期刊化草稿）”，不暗示 QA 完成、科学有效性或期刊接收。Research 或 Framework 不完整时，DOCX 必须保留对应的普通语言限制。

`draft.md` 仍是唯一可持续修改的正文 authority；`journal-manuscript.md` 与 `journal-manuscript.docx` 是 projections，不是 a second source of truth。Word 中的科学编辑必须回写到 draft 并重新运行 Synthesis/Framework/QA 所需的阶段，不能静默建立第二份 source of truth。Publication 完成后提供简短结果摘要，说明输入 revision、allowlist、清理动作、未解决限制、DOCX 验证结果和下一步。

## 失败恢复

遇到 Markdown/DOCX 内容不一致、视觉来源冲突、目标期刊指南过期或输入 revision 不明时暂停投影，保留已有 projection 和原因，返回研究者确认。不要覆盖原稿、删除旧 projection 或把排版冲突解释成科学结论。
