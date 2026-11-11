# DeepSeek Harness 接入

本配置根据已安装的官方 `@deepseek-ai/dsh-mcp-client` 文档核对。每个服务器使用一个插件实例，stdio连接并注册为 `mcp__服务器名__工具名`。

编辑 `examples/dsh.patch.yml` 的Python、server.py和环境路径，指向本机安装位置。保持NVivo与清洗两个独立实例。

```powershell
dsh --profile web --patch ./examples/dsh.patch.yml --dump-config
dsh --profile web --patch ./examples/dsh.patch.yml
```

首条用于检查合成配置，第二条启动带该工具的客户端。若客户端已有运行实例，将对应insert条目合并到所用profile的cordis.patch.yml，按客户端重载机制生效。正式合并前保留原配置备份。

NVivo后台处理可能超过默认60秒，因此示例设为1800000毫秒。该时限覆盖一次工具调用，材料批量规模仍需结合运行时间调整。MCP工具执行由本机完成，模型提供方可独立选择。

验证分层：Python stdio端到端调用已有实际测试；DSH配置合成另行核对。真实模型自主选择并完成整个研究工作流仍取决于客户端和模型。
