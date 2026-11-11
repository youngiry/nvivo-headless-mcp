---
name: nvivo-headless
description: Use the local NVivo MCP to create, import, code, read and verify native NVivo projects on Windows without controlling the desktop.
---

# NVivo后台使用

先调用nvivo_doctor，运行时变化后执行verify_live.py。sources承载原始可读文本，codes承载初码与归并，cases承载案例，memos承载有依据的研究过程。默认署名Shalom；整理时间用实际时间。

批量任务使用create → sync → checkpoint；精确原文quote和零起点occurrence定位编码，父代码先于子代码。已有工程全量替换走pipeline.py，保留备份及最终路径原生读回报告。资料清洗由独立material-cleaning工具负责。

验收正文、层级、编码覆盖及备忘关联，重合引用按覆盖范围比较。在NVivo中展开父节点“＋”查看下级；父节点0参考点可能表示编码位于子节点。并发客户端对同一工程串行运行。

README.md记录安装、环境和边界；docs/workflow.md记录可选的两插件组合流程。
