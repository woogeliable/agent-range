# V2 归档（legacy）

这里保留 AgentRange V2（提交 `146c1a1`）的代码，用于迁移参考：

- `adapters/`、`engine/`、`data/`、`web/`：旧版 Dify/Coze 兼容接口与四个确定性场景。
- `tests/`：旧版测试，未纳入当前 CI。它们依赖旧的 `server.py` 与目录结构，需要时可在隔离环境单独恢复运行。

V3 的 `/legacy/*` 兼容层将在 P3 基于这些代码重新实现，默认关闭。当前版本不导入此目录。

旧版文档：`V2升级说明.md`、`实施与测试记录.md`。
