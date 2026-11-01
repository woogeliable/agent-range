"""Lesson pack loading, public projection and the verifier."""
import json
import os

CHAPTERS = [
    {"id": "00", "title": "起点", "summary": "先建立心智模型：AI 应用的攻击面不是一条 API，而是一条上下文流水线。"},
    {"id": "01", "title": "提示注入与上下文边界", "summary": "用户输入、检索文档、工具返回值都会进入同一个上下文。谁被当成指令，谁就赢了。"},
    {"id": "02", "title": "RAG 与知识库", "summary": "检索不是只读：投毒、越权、引用伪造与外泄都发生在检索前后。"},
    {"id": "03", "title": "Agent 工具与权限", "summary": "Agent 的手比嘴危险。参数、身份、审批、出网，每一层都能被绕过。"},
    {
        "id": "04",
        "title": "Agent 生态与记忆",
        "summary": "MCP 工具描述、长期记忆、多 Agent 信任链——Agent 的供应链。",
    },
    {"id": "05", "title": "输出处理与下游", "summary": "模型输出不是终点。它会被渲染、被执行、被下游系统信任。"},
    {
        "id": "06",
        "title": "模型与数据面",
        "summary": "提示、PII、上下文预算与模型指纹，都是数据面的攻击面。",
        "planned": ["6.1 敏感信息与 PII", "6.2 模型指纹与提示提取", "6.3 上下文耗尽 / DoS"],
    },
    {
        "id": "07",
        "title": "防御工程与红蓝对抗",
        "summary": "把单点防御变成可度量、可回归的工程体系。",
        "planned": ["7.1 防御组合与消融", "7.2 可观测性与审计", "7.3 红蓝对抗与回归"],
    },
]

CHAPTER_MAP = {chapter["id"]: chapter for chapter in CHAPTERS}


def load(directory):
    lessons = {}
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(directory, name), encoding="utf-8") as handle:
            lesson = json.load(handle)
        for field in ("id", "chapter", "title", "type", "tasks"):
            if field not in lesson:
                raise ValueError("lesson %s missing %s" % (name, field))
        if lesson["id"] in lessons:
            raise ValueError("duplicate lesson id %s" % lesson["id"])
        lessons[lesson["id"]] = lesson
    return lessons


def score_for(stats):
    score = 100 - int(stats.get("hints_used", 0)) * 10
    if stats.get("solution_used"):
        score -= 30
    return max(0, score)


def _editable_text(lesson):
    target = lesson.get("target") or {}
    doc_id = target.get("editable_doc")
    if doc_id:
        for doc in target.get("docs") or []:
            if doc.get("id") == doc_id:
                return doc.get("text", "")
        return ""
    tool_id = target.get("editable_tool")
    if tool_id:
        for tool in target.get("mcp_tools") or []:
            if tool.get("name") == tool_id:
                return tool.get("description", "")
        return ""
    return None


def public_lesson(lesson, task_state=None, stats=None):
    """Projection safe to send to the browser: never include system prompts."""
    target = lesson.get("target") or {}
    task_state = task_state or {}
    stats = stats or {}
    quiz = lesson.get("quiz") or {}
    questions = []
    for question in quiz.get("questions") or []:
        questions.append(
            {
                "id": question["id"],
                "prompt": question["prompt"],
                "options": question["options"],
            }
        )
    return {
        "id": lesson["id"],
        "chapter": lesson["chapter"],
        "title": lesson["title"],
        "subtitle": lesson.get("subtitle", ""),
        "difficulty": lesson.get("difficulty", 1),
        "minutes": lesson.get("minutes", 10),
        "type": lesson.get("type", "chat"),
        "mapping": lesson.get("mapping") or [],
        "brief": lesson.get("brief") or {},
        "levels": lesson.get("levels") or ["vulnerable"],
        "default_level": lesson.get("default_level", "vulnerable"),
        "tasks": [
            {
                "id": task["id"],
                "title": task["title"],
                "done": bool(task_state.get(task["id"])),
            }
            for task in lesson.get("tasks") or []
        ],
        "hints_count": len(lesson.get("hints") or []),
        "hints_used": int(stats.get("hints_used", 0)),
        "solution_used": bool(stats.get("solution_used")),
        "score": score_for(stats),
        "source": lesson.get("source") or {},
        "target": {
            "name": target.get("name", "目标应用"),
            "persona": target.get("persona", "Agent"),
            "tools": target.get("tools") or [],
            "canary_prefix": target.get("canary_prefix", "AR"),
            "xss": bool(target.get("xss")),
            "echo": bool(target.get("echo")),
            "downstream": target.get("downstream", ""),
        },
        "editable_doc": bool(target.get("editable_doc") or target.get("editable_tool")),
        "editable_doc_id": target.get("editable_doc") or target.get("editable_tool"),
        "editable_doc_text": _editable_text(lesson),
        "editable_kind": "tool" if target.get("editable_tool") else "doc",
        "quiz": {"questions": questions} if questions else None,
    }


def _contains(value, needle):
    return str(needle).lower() in str(value).lower()


def _match_tool(call, spec):
    if call.get("tool") != spec.get("tool"):
        return False
    if "status" in spec and call.get("status") != spec["status"]:
        return False
    for key, expected in (spec.get("args_contain") or {}).items():
        if not _contains((call.get("args") or {}).get(key, ""), expected):
            return False
    return True


def evaluate(rule, ctx):
    if not isinstance(rule, dict):
        return False
    if "all" in rule:
        return all(evaluate(item, ctx) for item in rule["all"])
    if "any" in rule:
        return any(evaluate(item, ctx) for item in rule["any"])
    if "not" in rule:
        return not evaluate(rule["not"], ctx)

    world = ctx.get("world") or {}
    answer = ctx.get("answer") or ""
    canary = world.get("canary") or ""
    canary_b = world.get("canary_b") or ""

    if "canary_in_output" in rule:
        return bool(canary) and canary in answer
    if "canary_not_in_output" in rule:
        return bool(canary) and canary not in answer
    if "canary_b_in_output" in rule:
        return bool(canary_b) and canary_b in answer
    if "canary_b_not_in_output" in rule:
        return bool(canary_b) and canary_b not in answer
    if "memory_loaded" in rule:
        return bool((world.get("meta") or {}).get("memory_loaded"))
    if "memory_contains" in rule:
        needle = str(rule["memory_contains"]).lower()
        return any(needle in str(item).lower() for item in world.get("memory") or [])
    if "order_status" in rule:
        spec = rule["order_status"]
        order = (world.get("orders") or {}).get(str(spec.get("owner", "")).upper())
        return bool(order) and order.get("status") == spec.get("equals")
    if "sink_fired" in rule:
        sink = rule["sink_fired"]
        if any(item.get("sink") == sink for item in world.get("sinks") or []):
            return True
        return any(
            item.get("sink") == sink and item.get("type") == "sink.fired"
            for item in ctx.get("trace") or []
        )
    if "output_contains" in rule:
        return _contains(answer, rule["output_contains"])
    if "output_not_contains" in rule:
        return not _contains(answer, rule["output_not_contains"])
    if "last_user_message_not_contains" in rule:
        messages = [m for m in ctx.get("messages") or [] if m.get("role") == "user"]
        return bool(messages) and not _contains(messages[-1].get("content", ""), rule["last_user_message_not_contains"])
    if "no_user_message_contains" in rule:
        messages = [m for m in ctx.get("messages") or [] if m.get("role") == "user"]
        return all(not _contains(m.get("content", ""), rule["no_user_message_contains"]) for m in messages)
    if "tool_called" in rule:
        return any(_match_tool(call, rule["tool_called"]) for call in ctx.get("tool_calls") or [])
    if "tool_not_called" in rule:
        return not any(_match_tool(call, rule["tool_not_called"]) for call in ctx.get("tool_calls") or [])
    if "world_fact" in rule:
        spec = rule["world_fact"]
        return (world.get("facts") or {}).get(spec.get("name")) == spec.get("equals")
    if "world_fact_not" in rule:
        spec = rule["world_fact_not"]
        return (world.get("facts") or {}).get(spec.get("name")) != spec.get("equals")
    if "attempt_level" in rule:
        return ctx.get("level") == rule["attempt_level"]
    if "turns_at_least" in rule:
        return int(ctx.get("turns") or 0) >= int(rule["turns_at_least"])
    if "quiz_correct" in rule:
        return int((ctx.get("quiz") or {}).get("correct") or 0) >= int(rule["quiz_correct"])
    return False
