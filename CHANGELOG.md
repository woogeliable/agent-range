# Changelog

## 3.1.0 — 2026-11-01

P3：把 MVP 从 5 关扩到 12 关，并补上研究/对比所需的观测与重放能力。

### Added
- 7 个新关卡：`1.4` 过滤器绕过、`2.1` 知识库投毒、`2.2` 多租户检索越权、`3.1` 工具参数注入、`3.2` 混淆代理、`3.3` SSRF、`5.1` 不安全输出 → XSS。
- 工具返回二次入上下文：`crm.query` 的备注在漏洞版可产生指令，加固版按 untrusted 数据拒绝。
- 虚拟世界新增 `canary_b`（B 租户金丝雀）、`customers`、`sinks`、`meta.blocklist / xss / echo`；检索支持 owner 过滤与 boost。
- 新工具：`crm.query`；`http.fetch` 假网络新增 `169.254.169.254`、`10.0.0.5`、`admin.internal`。
- 新 verifier：`canary_b_in_output`、`canary_b_not_in_output`、`world_fact_not`、`sink_fired`。
- API：`POST /api/attempts/{id}/sinks`、`POST /api/attempts/{id}/replay`、`GET /api/model/context`。
- 前端：trace 类型过滤与证据高亮、实验记录、反事实重放对比、真实模型只读对照面板、XSS 下游渲染按钮。
- 70 项自动化测试。

### Changed
- 版本号 3.1.0；`Server: AgentRange/3.1`。
- 输入归一化：NFKC + 去零宽 + Base64 解码后交给模型，黑名单仍看原始串（1.4 的教学点）。
- trace 新增 `context.tool_result`、`sink.fired` 事件。
- 反事实重放只复制用户消息，不复制源实验的助手回答或世界状态。

### Deferred
- 研究台批量评测、ASR/良性误拦率、导出与回归门禁（P4）。
- 剩余 13 关、讲师视图、Docker、双语（P5）。

## 3.0.0-slice — 2026-11-01

P1–P2 纵向切片：从「Dify/Coze 接口模拟器」重构为课程化 AI 应用安全靶场。

### Added
- 全新 `arange/` 运行时：确定性指令决策模型、信任标签上下文、沙箱工具、逐轮 trace。
- 5 个可交互关卡：`0.1` 第一血、`0.2` 信任边界测验、`1.1` 直接注入、`1.2` 系统提示泄露、`1.3` 间接注入。
- 每关 3 个任务、服务端 verifier、3 级提示、参考解法、4 档防御与源码 diff。
- 游客会话、课程地图、关卡页、任务/提示/源码/观测面板、移动端布局。
- 每次 attempt 独立金丝雀、世界快照、重置；进度与得分持久化。
- 可选真实模型的严格 HTTPS provider（默认关闭，切片阶段只读）。
- 42 项自动化测试（运行时、关卡、API、安全头、provider）。
- CSP、CSRF 头、会话 Cookie、请求体上限、静态目录穿越防护。

### Changed
- 入口从环境变量控制令牌 + 手动粘贴，改为自动游客会话。
- 安全教学从「关键词命中」改为「指令提取 → 策略消解 → 工具执行」。
- V2 代码归档到 `legacy/v2/`，不再被当前服务导入。

### Deferred
- `/legacy/*` Dify/Coze 兼容层（P3）。
- 研究台、语料批量评测、ASR 报表（P3–P4）。
- 剩余 20 关与讲师视图（P3–P5）。
