# Agent Range

本地运行的多平台 AI API 安全测试靶场。Python 标准库实现，不依赖 GitHub、第三方包或外部服务。

项目位于本仓库根目录。

## 启动

```bash
cd agent-range
python3 server.py
```

服务监听 `0.0.0.0:8787`。打开 `http://localhost:8787` 进入控制台。

## 路由

| 目标 | 路由形式 | 兼容/用途 |
|---|---|---|
| 控制台 | `/` | 统一配置页面 |
| Coze | `/coze/*` | `/v1/chat/completions`、`/open_api/v2/chat`；根路径下相同 API 仍作为旧版 Coze 别名 |
| Dify | `/dify/*` | `/v1/info`、`/v1/parameters`、`/v1/meta`、`/v1/site`、`/v1/chat-messages`、`/console/api/login`、`/console/api/apps` |
| HTTP | `/http/*` | 本地健康检查与鉴权回显；绝不转发外部网络 |
| 控制台管理 API | `/control/*` | 状态、目标配置、令牌管理、种子重置、控制台试对话 |

在 Dify 客户端中把 API Base URL 设置为 `http://localhost:8787/dify`；Coze Base URL 为 `http://localhost:8787/coze`。原来使用根路径的 Coze 客户端无需改路径。

## 种子凭证

- Dify API：`app-demo-dify-token`
- Dify 控制台/工作空间发现：`console-admin-token`
- Coze：`coze-demo-token`
- HTTP：`http-demo-token`
- Dify 模拟登录：用户名 `admin`，密码 `admin`

令牌在本机明文模拟保存于 `data/state.json`，仅供测试；不要用于真实系统或生产环境。管理 API 刻意简化为本地控制面，没有真实身份认证。请勿将该靶场暴露到公网。

## Dify 示例

```bash
curl http://localhost:8787/dify/v1/info \
  -H 'Authorization: Bearer app-demo-dify-token'

curl http://localhost:8787/dify/v1/chat-messages \
  -H 'Authorization: Bearer app-demo-dify-token' \
  -H 'Content-Type: application/json' \
  -d '{"query":"你好","response_mode":"blocking","user":"tester"}'
```

把 `response_mode` 改成 `streaming` 可测试 SSE。Dify 工作空间发现可通过 `GET /dify/console/api/apps` 搭配 `console-admin-token` 调用；模拟登录 `POST /dify/console/api/login` 接收 `{"email":"admin","password":"admin"}`。

## 场景档位

1. **正常**：常规合成回复。
2. **泄露提示词**：回显当前配置的系统提示词。
3. **知识外泄**：输出固定合成知识片段和专用演示标记，不含真实秘密。
4. **工具越权**：返回越权尝试的安全模拟结果；不会执行真实命令、读取文件或调用工具。
5. **全部拒答**：对每条消息统一拒绝。
6. **未发布**：公开 `/v1/*` 应用端点返回未发布/找不到；控制台管理端点仍可访问。

每个平台分别保存提示词与档位。控制台的“还原种子”会恢复全部默认提示词、档位、示例令牌，并清空请求日志。状态保存在 `data/state.json`。

## 扩展适配器

适配器接口固定为 `adapters/base.py` 中的 `Adapter.handle(handler, method, path, query, body)`，并提供 `name`、`label`、`prefix`。注册表、HTTP 路由、控制台平台切换、目标配置与种子档案均由已注册适配器自动生成。

新增 MCP 或 OpenAI 兼容端点时，只需：

1. 在 `adapters/` 新建一个实现 `Adapter` 的文件；
2. 在 `adapters/__init__.py` 加一行导入并注册，例如：`from .mcp import MCPAdapter; register(MCPAdapter)`。

无需改服务路由或控制台；新增适配器会自动获得正常场景种子档案，并显示在平台切换、令牌创建与配置卡中。`/http/*` 是本地回显靶标，不是通用外网代理。

## 测试

```bash
python3 -m unittest discover -s tests -v
```
