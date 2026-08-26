---
name: chemical-review-publication
description: "Project a confirmed chemical review draft into reader-ready Markdown and an openable DOCX without changing its science."
disable-model-invocation: true
---

# Chemical Review Publication

Publication 是 user-invoked（用户主动调用）的交付投影，不是 Chemical Review 的第六个科学阶段。它把已经确认的 `draft.md` 整理成普通期刊读者可读的 `journal-manuscript.md`，再按宿主已有的文档能力生成 `journal-manuscript.docx`。核心 Markdown 资产仍然是唯一正文权威，Publication 不回写 draft、Research、Framework 或 QA 资产。

## 输入边界与输出

默认只读：

- 用户指定的 canonical `draft.md`；
- 研究者明确 allowlist 的 confirmed brief、Research/Framework handoff、QA 反馈、引用/图表材料；
- 若需目标期刊适配，研究者确认后允许读取的当前官方指南。

不要主动读取无关 history、global memory、parent context、凭据、cookie、session、sibling checkout 或未列出的旧稿。缺材料时报告缺口，不从隐藏上下文补写。

默认产物是：

1. `journal-manuscript.md`：可检查、可编辑的期刊可读整篇稿件；
2. `journal-manuscript.docx`：由该 Markdown projection 一次生成的 Word 文档；这是 a one-time projection，不是第二份正文权威。

DOCX 是一次性 projection，不是第二份正文数据库。若 Word 中发现科学修改，先回到 `draft.md` 完成科学修订，再重新投影。

## 渐进读取

先读取本页，再按任务需要读取：

1. [`clean-projection.md`](clean-projection.md)：内部标签清理、证据语义保留和编辑边界；
2. [`journal-and-visuals.md`](journal-and-visuals.md)：中性期刊、目标期刊确认、语言和视觉资产；
3. [`docx-and-boundary.md`](docx-and-boundary.md)：DOCX 映射、打开验证、QA 时序和 canonical ownership。

Publication 不自动运行 QA、不自动查新文献、不自动翻译，也不因为排版完成而声称 scientific validity 或 journal acceptance。

## 推荐工作回合

1. 核对输入 draft 的 revision、语言、Research/Framework 完整性和 allowlist；明确这是 QA 前还是 QA 后的投影。
2. 按 `clean-projection.md` 把内部流程信息改写为 ordinary scientific language（普通科学语言）；保留限制、不确定性、来源边界和模型假设。
3. 按 `journal-and-visuals.md` 选择中性期刊路径或经过确认的目标期刊路径，检查图、表、scheme、caption 与引用关系。
4. 写出并检查 `journal-manuscript.md`，再将同一内容投影为 DOCX；不要让 Word 版本反过来成为正文权威。
5. 在 handoff 或结果摘要中说明清理了什么、保留了什么、哪些材料缺失，以及下一步是科学修订、QA 还是仅交付。

## 编辑边界与完成契约

Publication 可以重写摘要、调整章节顺序、合并重复段落、整理表格/图题/引用/参考文献和删除内部标签。它不得新增未经支持的科学主张或文献，删除关键限制，改变核心判断，将 `MODEL_HYPOTHESIS` 写成来源事实，或把局部/partial-scope 结果包装成完整综述。

没有目标期刊时使用中性的 review article 结构。有目标期刊时，只有研究者确认后才读取当前官方指南。默认保持输入稿件的语言与术语；翻译是另一个明确任务。

完成 Publication 表示两个 projection 可读、科学含义没有漂移、DOCX 可打开且内部元数据已清理；它不表示 draft 已通过 QA、科学上正确或会被期刊接收。
