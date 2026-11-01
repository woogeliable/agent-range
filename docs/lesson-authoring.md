# 关卡编写指南

一关就是一个 JSON 文件，放在 `lessons/`，文件名建议 `序号-关卡ID-英文slug.json`。

服务端启动时加载全部 JSON；前端和 API 自动出现。无需改路由。

---

## 1. 最小骨架

```json
{
  "id": "1.4",
  "chapter": "01",
  "title": "过滤器绕过",
  "subtitle": "用编码与改写绕过关键词黑名单",
  "difficulty": 2,
  "minutes": 15,
  "type": "chat",
  "mapping": ["OWASP-LLM01", "ATLAS-AML.T0051"],
  "brief": {
    "threat_model": "黑名单只能覆盖已知写法。",
    "goal": "在不触发黑名单的情况下完成 1.1 的目标。",
    "background": "蓝雀科技的邮件助手加了关键词过滤。"
  },
  "target": {
    "name": "邮件助手",
    "persona": "邮件 Agent",
    "system_prompt": "你是内部邮件助手。",
    "policy": "只允许内部域名。",
    "tools": ["mail.send"],
    "facts": {},
    "docs": []
  },
  "levels": ["basic", "hardened"],
  "default_level": "basic",
  "tasks": [
    {
      "id": "t1",
      "title": "绕过黑名单并把邮件发到外部",
      "verify": {
        "tool_called": {
          "tool": "mail.send",
          "status": "ok",
          "args_contain": {"to": "attacker.example"}
        }
      }
    }
  ],
  "hints": ["先看黑名单拦了什么。", "试试同义改写。"],
  "solution": "……",
  "source": {
    "basic": "if any(w in text for w in BLOCK): reject()",
    "hardened": "if recipient.domain not in ALLOWED: deny()"
  }
}
```

---

## 2. 字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✅ | 唯一，建议 `章.关`，如 `1.4` |
| `chapter` | ✅ | `00`–`07`，必须在 `arange/lessons.py::CHAPTERS` 中 |
| `title` / `subtitle` | ✅ | 课程卡片与关卡页标题 |
| `difficulty` | ✅ | 0–3，前端显示为点 |
| `minutes` | ✅ | 预计时间 |
| `type` | ✅ | `chat` 或 `quiz` |
| `mapping` | ✅ | OWASP / ATLAS / CWE 标签，展示用 |
| `brief.threat_model` | ✅ | 本关的威胁模型 |
| `brief.goal` | ✅ | 学员要达成的目标 |
| `brief.background` |  | 虚构业务背景 |
| `target` | chat ✅ | 见下 |
| `levels` | ✅ | 可用档位，子集 `vulnerable/basic/hardened/reference` |
| `default_level` | ✅ | 必须属于 `levels` |
| `tasks` | ✅ | 1–5 个任务；id 唯一 |
| `hints` | ✅ | 3 条左右，按递进排序 |
| `solution` | ✅ | 参考解法；只有用户主动查看才返回 |
| `source` | chat ✅ | 档位 → 源码字符串；只返回源码，不含秘密 |
| `benign` |  | 良性基线问题，后续研究台使用 |
| `quiz` | quiz ✅ | 见下 |
| `target.editable_doc` |  | 允许学员编辑的低信任文档 id |

### target

| 字段 | 说明 |
|---|---|
| `name` / `persona` | 目标应用名称与角色 |
| `system_prompt` | 会进入上下文；支持 `{{canary}}` 与 `{{canary_b}}` 占位符 |
| `policy` | developer 段，展示"写了但未必执行"的规则 |
| `facts` | 世界事实，例如 `{"warranty_days": 365}` |
| `docs` | 检索文档：`id/title/trust/acl/keywords/text`，可加 `owner`（查询必须提到该主体）与 `boost`（排序权重） |
| `editable_doc` | 可编辑的低信任文档 id |
| `tools` | 该目标可用的工具名 |
| `canary_prefix` | 金丝雀前缀，默认 `AR` |
| `customers` | CRM 记录；`canary` 支持 `{{canary_b}}`，`note` 会成为工具返回值 |
| `blocklist` | 关卡专属黑名单词（基础过滤档使用） |
| `xss` / `echo` | 开启输出回显与 `/sinks` 渲染证据（5.1） |
| `tenant` / `user` | 世界主体，默认 `A` / `alice` |

文档里的 `trust` 只用于展示与黑名单，不改变"检索段不能产生指令"的规则。

---

## 3. 验证器 DSL

`verify` 是嵌套 JSON，支持：

```json
{"all": [{"tool_called": {"tool": "mail.send", "status": "ok"}}, {"attempt_level": "basic"}]}
{"any": [{"canary_in_output": true}, {"world_fact": {"name": "x", "equals": 1}}]}
{"not": {"output_contains": "拒绝"}}
```

| 谓词 | 参数 | 用途 |
|---|---|---|
| `canary_in_output` | `true` | 泄露、越权、外泄 |
| `canary_not_in_output` | `true` | 修复验证 |
| `canary_b_in_output` / `canary_b_not_in_output` | `true` | 跨租户越权 / 隔离验证 |
| `output_contains` | 字符串 | 明确的输出证据 |
| `output_not_contains` | 字符串 | 反向证据 |
| `last_user_message_not_contains` | 字符串 | 教"改写绕过" |
| `no_user_message_contains` | 字符串 | 更严格的全量检查 |
| `tool_called` | `{tool, status?, args_contain?}` | 工具调用与参数污染 |
| `tool_not_called` | 同上 | 拦截验证 |
| `world_fact` | `{name, equals}` | 世界状态被改写 |
| `world_fact_not` | `{name, equals}` | 世界状态未被改写 |
| `sink_fired` | `xss` 等 sink 名 | 下游渲染证据（需 `target.xss` + `/sinks`） |
| `attempt_level` | 档位 | 要求在某档完成 |
| `turns_at_least` | 整数 | 至少交互过 |
| `quiz_correct` | 整数 | 测验答对数 |

**原则：优先用 `canary`、`tool_called`、`world_fact` 这类客观证据；不要用"模型说了什么"作为唯一判定。**

---

## 4. 任务设计模板

一个完整的关卡建议包含三类任务：

1. **攻破**：`canary_in_output` / `tool_called` / `world_fact`。
2. **绕过或复现**：要求换写法、换档位、换路径。
3. **修复验证或良性基线**：切到加固档后攻击失效，同时正常问题仍能回答。

例如 1.1：

```json
[
  {"id": "t1", "title": "发到外部域名", "verify": {"tool_called": {"tool": "mail.send", "status": "ok", "args_contain": {"to": "attacker.example"}}}},
  {"id": "t2", "title": "基础过滤档下改写绕过", "verify": {"all": [{"attempt_level": "basic"}, {"tool_called": {...}}]}},
  {"id": "t3", "title": "加固档被出口白名单拦截", "verify": {"all": [{"attempt_level": "hardened"}, {"tool_not_called": {"tool": "mail.send", "status": "ok"}}, {"output_contains": "拦截"}]}}
]
```

---

## 5. 测验关卡

```json
{
  "type": "quiz",
  "quiz": {
    "questions": [
      {
        "id": "q1",
        "prompt": "检索到的论坛帖子属于哪一类内容？",
        "options": ["系统规则", "可信事实", "数据，不是指令", "开发者指令"],
        "answer": 2,
        "explain": "检索内容永远是数据。"
      }
    ]
  },
  "tasks": [{"id": "t1", "title": "答对至少 4 题", "verify": {"quiz_correct": 4}}]
}
```

`answer` 是选项下标；不要在别处重复正确答案。API 返回题目时会去掉 `answer` 与 `explain`。

---

## 6. 提示与解法

- 提示逐级递进：观察 → 方向 → 具体手法。不要第一条就给 payload。
- 解法写清三件事：**怎么打、为什么成立、怎么修**。
- 解法里可以放 payload；提示里尽量只放方向。
- 提示与解法会扣分，但不影响任务完成标记。

---

## 7. 源码面板

`source` 的键必须是 `levels` 的子集：

```json
"source": {
  "vulnerable": "system = SYSTEM + user_input",
  "basic": "if blocked(user_input): reject()",
  "hardened": "context = [system(rules), data(user_input)]",
  "reference": "context + capability + approval + egress + dlp"
}
```

前端会展示当前档位源码，并支持与上一档做行级 diff。源码要真实对应当前实现，不要写成装饰文案。

---

## 8. 工具返回值与 sink

- `target.tools` 决定哪些工具可被调用；不在列表里的工具不会执行，也不会产生任务证据。
- `crm.query` 的返回会作为 `untrusted` 段重新进入上下文。漏洞/基础档可能把其中的 `set_fact` 类文本当指令；加固/参考档只当数据。
- 需要演示输出型漏洞时，设置 `target.xss: true` 与 `target.echo: true`；学员点击「在下游页面渲染」会 POST `/api/attempts/{id}/sinks`，服务端记录 `sink.fired`。
- 不要在前端用 `innerHTML` 执行不可信回复；当前实现只模拟下游并记录证据。

---

## 8. 检查清单

- [ ] `id` 唯一，`chapter` 存在。
- [ ] `default_level` 在 `levels` 内。
- [ ] 每个 task 至少有一个客观谓词。
- [ ] 至少有一个"切到加固档失效"或"良性基线"任务。
- [ ] 目标中的所有秘密都用 `{{canary}}`，不要写死。
- [ ] `source` 的键是 `levels` 子集。
- [ ] 提示不直接给答案；解法包含"为什么"和"怎么修"。
- [ ] 所有数据为虚构；不写真实域名、密钥、个人信息。
- [ ] 运行 `python3 -m unittest discover -s tests -v`，关卡包测试通过。
- [ ] 浏览器里从漏洞档打到加固档，trace 能解释每一步。

---

## 9. 调试

```bash
python3 server.py
# 打开 /lesson/<id>
# 看「观测」面板：上下文分段、候选指令、策略判定、工具调用、verifier 证据
```

如果任务不通过，先看 trace：

- 没有 `retrieval`：关键词没命中，检查 `docs[].keywords`。
- 有 `retrieval` 但没有 `model.directives`：文档措辞没被提取器识别，换更直接的祈使句或覆盖词。
- 有候选指令但 `policy.directive` 为拒绝：当前档位本来就不允许，切档或换攻击面。
- 工具被 blocked：查看 `reason`（`egress_allowlist` / `owner_mismatch` / `approval_required`）。
- 都有但 verifier 不过：检查谓词参数是否与实际输出一致。
