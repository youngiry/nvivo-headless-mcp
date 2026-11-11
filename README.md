# NVivo Headless MCP

用标准 MCP stdio 在 Windows 后台创建、导入、编码、保存和重新打开 NVivo 工程。适用于支持本地 MCP 的智能体客户端，模型可由 DeepSeek、Qwen、Kimi 或其他提供方驱动。

作者：Shalom。版本：0.1.0。真实验证环境：Windows、NVivo 15.6.1.3、LocalDB QSRNVivo20.6、Python 3.13。软件运行时与有效许可由使用者本机提供。本仓库提供适配器源码；NVivo 商业软件及 DLL 由本机安装提供。其他 NVivo 版本需先运行自检及真实测试。

## 安装

```powershell
git clone https://github.com/youngiry/nvivo-headless-mcp.git
cd nvivo-headless-mcp
.\install.ps1 -NvivoInstallDir "D:\QSR\NVivo 15"
```

安装器生成 `config.local.json`。把其中的 `mcpServers.nvivo_headless` 合入客户端 MCP 设置。已有设置保留，再新增这一项。客户端若采用 TOML，转换同名 command、args、env 字段即可。

```powershell
$env:NVIVO_INSTALL_DIR = "D:/QSR/NVivo 15"
.\.venv\Scripts\python.exe doctor.py
.\.venv\Scripts\python.exe verify_live.py
```

真实测试创建独立测试工程，验证中文、emoji后的引文位置、重复句定位、父子代码、编码重试、备忘及保存重开；测试输出在 `results/native_mcp_acceptance.json`。运行前关闭目标测试工程。

## 使用

先调用 `nvivo_doctor`，再调用 `nvivo_create_project`。通过 `nvivo_sync_coding` 批量导入 sources、memos、codes、cases、codings，最后调用 `nvivo_checkpoint`。sources 放完整可读材料，memos 放研究判断过程，codes 放主题和初码，cases 放案例及属性。编码通过 source、code、quote 和零起点 occurrence 指向精确原文。父代码排在子代码之前，各对象使用唯一名称。最小输入见 `examples/bundle.json`。

现有研究项目需要完整替换时使用 `pipeline.py --input 输入.json --project 最终.nvp --report 验收.json --author Shalom`。该入口创建候选、原生验证、备份、替换、从最终路径重开，再更新最近项目。MCP 的 sync 为增量合并，同名正文变化时要求先明确处理；完整替换适用于已经整理好的全量输入。

13个工具覆盖环境检查、创建、项目检查、来源列表/读取、代码列表/新增、文本导入、备忘、精确编码、引用读取、批量同步和保存核验。

在 NVivo 的代码树中点击上级节点左侧“＋”查看下级编码。上级节点自身的参考点可为0，下级节点承载实际编码；双击具体代码查看原文参考点。

## 范围和恢复

材料清洗是独立插件：[Material Cleaning MCP](https://github.com/youngiry/material-cleaning-mcp)。本工具接收已经准备好的文本。组合方法见 [工作流](docs/workflow.md)。

NVivo 插件运行于安装软件的 Windows 机器，支持同机 stdio MCP；云端聊天网页需要能连接本地工具的客户端。DeepSeek 是模型提供方，实际 MCP 接入由 Harness/客户端实现，配置字段以客户端版本为准。标准协议测试通过代表传输兼容；各品牌客户端的端到端适配另行验证。

`NVIVO_WORKSPACE` 限定 MCP 工程目录；默认作者为 Shalom，可通过 `NVIVO_AUTHOR` 设置。安装目录使用 `NVIVO_INSTALL_DIR`，LocalDB 可通过 `NVIVO_LOCALDB_EXE` 与 `NVIVO_LOCALDB_INSTANCE` 配置。备份位于 workspace/native_runs 或报告旁的 native_runs。并发使用同一个工程应由客户端串行排队，NVivo前台打开的工程应先关闭。资料、报告及备份保留在本机。

每次换机、升级 NVivo 或变更运行时后先执行真实测试，报告通过后再处理正式项目。备忘记录实际研究过程及整理时间。

DeepSeek Harness专用示例见 [接入说明](docs/deepseek-harness.md) 和 `examples/dsh.patch.yml`。
