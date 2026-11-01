# Changelog

## 3.2.0 — 2026-11-02

第 4 章全部、第 5 章全部上线：课程从 12 关扩到 17 关，补齐 MCP、记忆、多 Agent、SQL 下游与幻觉动作。

### Added
- 5 个新关卡：`4.1` MCP 工具投毒、`4.2` 记忆投毒、`4.3` 多 Agent 信任链、`5.2` 输出当命令 → SQL 注入、`5.3` 幻觉导致错误动作。
- 运行时原语：MCP 工具描述进入上下文并可按关卡编辑；长期记忆写入 SQLite `memories` 表并跨 attempt 注入；`agent.ask` 返回子 Agent 报告；`refund.create` 沙箱退款。
- 四档语义：漏洞版信任工具描述/记忆/子 Agent、把输出原样拼 SQL、引用幻觉政策；基础过滤只挡显式注入；加固版把上述内容一律标为 untrusted 数据，并校验引用政策；参考实现全开。
- 新 verifier：`memory_loaded`、`memory_contains`、`order_status`；`sink_fired` 支持 `sink: "sql"`。
- trace：`context.agent_message`、`memory.written`、`sink.fired(sql)`；上下文新增 `mcp` 与 `memory` 段。
- API：`/sinks` 支持 `sql`，并校验关卡确实声明了下游 SQL；`public_lesson` 暴露 `editable_kind` 与 `meta.downstream`。
- 前端：MCP 工具描述编辑器、SQL 模拟器按钮、子 Agent/记忆事件展示；课程地图第 4、5 章标为已上线。
- 88 项自动化测试（新增 `tests/test_p4.py`，覆盖 5 关 × 四档）。

### Changed
- 版本号 3.2.0；`Server: AgentRange/3.2`；首页品牌同步。
- 课程页说明改为「第 4、5 章已全部上线；第 6、7 章规划中」，不再把第 4 章标记为 planned。
- 记忆在新建/重置 attempt 时注入最近 6 条，重置不清空记忆（4.2 的教学点）。

### Fixed
- 子 Agent 消息与工具返回被二次解析时，denied 结果会累加回本轮，加固版能正确显示「已忽略未验证的子 Agent 指令」。
- `refund.create` 在缺少金额或金额非正数时返回 `invalid_amount`，不再产生 0 元退款。

### Deferred
- 第 6–8 章剩余 8 关。
- 研究台批量评测、ASR/良性误拦率、导出与回归门禁（P4）。
- 讲师视图、Docker、双语（P5）。

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
