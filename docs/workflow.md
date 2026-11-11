# 两个独立插件的组合工作流

1. 保存来源原件、来源说明和研究记录，冻结本次输入。
2. 调用 Material Cleaning MCP：逐来源确定正文边界，将已有研究引文作为 protected passages 输入；保存清洗审计，核查正文连贯性与引文。
3. 将清洗后的 documents 转为 NVivo sources。将已有编码的 source、code 与清洗输出的 quote、occurrence 对齐。研究判断及归并依据写成 memos，按实际记录保留来源/代码/案例关联。
4. 调用 NVivo Headless MCP 的 doctor、create、sync、checkpoint；全量替换使用 pipeline CLI。作者默认为 Shalom。
5. 验收原生重新打开、全文、代码层级、引用覆盖、备忘链接及案例属性。重合引用可由NVivo合并，应比较覆盖范围。
6. 在NVivo展开代码树的“＋”，双击具体代码检查原文。验证通过的最终文件作为交付，旧工程按用户授权另行整理。

每个插件均可单独使用。清洗工具只返回材料；NVivo工具负责软件工程。人工选定正文边界、研究编码与解释仍以实际研究材料为依据。
