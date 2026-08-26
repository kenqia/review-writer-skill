# Research Preflight

预检只回答一个问题：当前 confirmed brief 所需的最佳 Research 路线和有现实价值的备选路线能不能顺利走通。先从 brief 的 evidence expectations 推出需要验证的能力，再用少量真实探针或明确的本地检查，写一张研究者看得懂的表；不要因为熟悉某个 provider 就探测所有路线。每行结果只能是 `pass`、`failure` 或 `not-verified`，并附实际证据。

```markdown
| 能力 | 通过标准 | 结果（通过/失败/未验证） | 对本轮的影响 | 官方入口或配置说明 | 下一步 |
| --- | --- | --- | --- | --- | --- |
| metadata discovery | 用 brief 相关词返回至少一条可解释、可去重的 identity；记录实际响应 | ... | ... | ... | ... |
| chemistry term lookup | 返回可复核的 synonym/entity，并说明 identity/版本 | ... | ... | ... | ... |
| legal full-text route | 对一条候选给出合法 landing/PDF 路径和访问依据，不绕过权限 | ... | ... | ... | ... |
| parser route | 对一份授权 fixture PDF 产出带 locator 的阅读文本，并标成 excerpt | ... | ... | ... | ... |
```

推荐检查 OpenAlex、Semantic Scholar 或 Crossref 的一条 metadata 路线，PubChem 或 ChEBI 的术语路线，Europe PMC、Unpaywall 或 CORE 的合法全文路线，以及项目实际授权 PDF 的 MinerU 解析路线。没有配置也如实记录；不要把“字段存在”写成“调用成功”。

每一行都必须有实际探针或明确的 not-verified 原因。结果表里写 official setup page、变量名、项目外的 `.env.local` 或进程环境，以及回来后的 rerun 方式。只报告凭据存在/缺失和风险，不写值，不保留 signed URL、cookie 或完整错误日志。字段存在、provider 名称、doctor 输出或安装包存在都不是 pass 证据。

## 预检后的选择

- `configure_and_continue`：研究者去官方入口配置，当前对话停在这里；配置回来后重新做预检。
- `accept_degraded`：研究者明确接受某项能力缺失，并看到它会缩小哪些论点或全文覆盖。
- `pause`：暂不继续。

配置选择本身不等于正式开始。预检重新通过、或研究者接受了清楚写出的降级后，再单独询问 `confirm_formal_start`（也接受同义的自然语言确认）。没有这一步，先不做正式 discovery、全文队列或解析；失败路线也不能自动换成次优路线。

如果探针超时、返回 malformed 结果或只能检查本地存在，写 `not-verified`，说明影响和下一次动作，不把它当 pass。完成本页的标准是：表格足以让研究者知道哪些能力可用、哪些没过、影响是什么、该去哪里配置以及何时回来。
