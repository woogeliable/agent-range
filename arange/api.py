"""JSON API for the range."""
import re
import time
from urllib.parse import parse_qs

from . import config
from . import lessons as lesson_mod
from .runtime import model as model_mod


class ApiError(Exception):
    def __init__(self, status, code, message=""):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code


class Api:
    def __init__(self, store, engine, lessons, provider, version):
        self.store = store
        self.engine = engine
        self.lessons = lessons
        self.provider = provider
        self.version = version

    # ---- dispatch ---------------------------------------------------------
    def handle(self, method, path, query, body, user):
        path = path.rstrip("/") or "/"

        if path == "/api/health":
            self._require(method, "GET")
            return 200, {
                "ok": True,
                "version": self.version,
                "time": int(time.time()),
                "lessons": len(self.lessons),
            }

        if path == "/api/me":
            self._require(method, "GET")
            return 200, self._me(user)

        if path == "/api/model/status":
            self._require(method, "GET")
            return 200, self.provider.status()

        if path == "/api/model/context":
            self._require(method, "GET")
            return 200, self._model_context(user, query)

        if path == "/api/lessons":
            self._require(method, "GET")
            return 200, self._course(user)

        match = re.match(r"^/api/lessons/([A-Za-z0-9._\-]+)$", path)
        if match:
            self._require(method, "GET")
            return 200, self._lesson_detail(user, match.group(1))

        match = re.match(r"^/api/lessons/([A-Za-z0-9._\-]+)/attempts$", path)
        if match:
            self._require(method, "POST")
            return 201, self._create_attempt(user, match.group(1), body)

        match = re.match(r"^/api/lessons/([A-Za-z0-9._\-]+)/quiz$", path)
        if match:
            self._require(method, "POST")
            return 200, self._quiz(user, match.group(1), body)

        match = re.match(r"^/api/lessons/([A-Za-z0-9._\-]+)/solution$", path)
        if match:
            self._require(method, "POST")
            return 200, self._solution(user, match.group(1))

        match = re.match(r"^/api/lessons/([A-Za-z0-9._\-]+)/hint$", path)
        if match:
            self._require(method, "POST")
            return 200, self._hint_lesson(user, match.group(1))

        match = re.match(r"^/api/attempts/([A-Za-z0-9_\-]+)$", path)
        if match:
            self._require(method, "GET")
            return 200, self._attempt_detail(user, match.group(1))

        match = re.match(r"^/api/attempts/([A-Za-z0-9_\-]+)/messages$", path)
        if match:
            self._require(method, "POST")
            return 200, self._message(user, match.group(1), body)

        match = re.match(r"^/api/attempts/([A-Za-z0-9_\-]+)/reset$", path)
        if match:
            self._require(method, "POST")
            return 200, self._reset(user, match.group(1))

        match = re.match(r"^/api/attempts/([A-Za-z0-9_\-]+)/hint$", path)
        if match:
            self._require(method, "POST")
            return 200, self._hint(user, match.group(1))

        match = re.match(r"^/api/attempts/([A-Za-z0-9_\-]+)/sinks$", path)
        if match:
            self._require(method, "POST")
            return 200, self._sink(user, match.group(1), body)

        match = re.match(r"^/api/attempts/([A-Za-z0-9_\-]+)/replay$", path)
        if match:
            self._require(method, "POST")
            return 201, self._replay(user, match.group(1), body)

        raise ApiError(404, "not_found", "接口不存在")

    def _require(self, method, expected):
        if method != expected:
            raise ApiError(405, "method_not_allowed", "方法不允许")

    def _lesson(self, lesson_id):
        lesson = self.lessons.get(lesson_id)
        if not lesson:
            raise ApiError(404, "lesson_not_found", "关卡不存在")
        return lesson

    def _attempt(self, user, attempt_id):
        attempt = self.store.get_attempt(attempt_id, user["id"])
        if not attempt:
            raise ApiError(404, "attempt_not_found", "实验不存在或已过期")
        return attempt

    # ---- payloads ---------------------------------------------------------
    def _me(self, user):
        summary = self._summary(user)
        return {
            "user": {"id": user["id"], "handle": user["handle"]},
            "progress": summary,
            "model": self.provider.status(),
            "version": self.version,
        }

    def _summary(self, user):
        rows = self.store.progress(user["id"])
        done = {(row["lesson_id"], row["task_id"]) for row in rows}
        total_tasks = 0
        done_tasks = 0
        lessons_done = 0
        score = 0
        for lesson in self.lessons.values():
            tasks = lesson.get("tasks") or []
            total_tasks += len(tasks)
            lesson_done = 0
            for task in tasks:
                if (lesson["id"], task["id"]) in done:
                    lesson_done += 1
            done_tasks += lesson_done
            if tasks and lesson_done == len(tasks):
                lessons_done += 1
            stats = self.store.stats(user["id"], lesson["id"])
            if lesson_done or stats.get("hints_used") or stats.get("solution_used"):
                score += lesson_mod.score_for(stats)
        return {
            "tasks_done": done_tasks,
            "tasks_total": total_tasks,
            "lessons_done": lessons_done,
            "lessons_total": len(self.lessons),
            "score": score,
            "percent": round(done_tasks * 100 / total_tasks, 1) if total_tasks else 0,
        }

    def _task_list(self, user, lesson):
        state = self.engine.task_state(user["id"], lesson)
        return [
            {"id": task["id"], "title": task["title"], "done": bool(state.get(task["id"]))}
            for task in lesson.get("tasks") or []
        ]

    def _course(self, user):
        self.store.purge_expired()
        rows = self.store.progress(user["id"])
        done = {(row["lesson_id"], row["task_id"]) for row in rows}
        grouped = {chapter["id"]: [] for chapter in lesson_mod.CHAPTERS}
        for lesson in sorted(self.lessons.values(), key=lambda item: item["id"]):
            tasks = lesson.get("tasks") or []
            completed = sum(1 for task in tasks if (lesson["id"], task["id"]) in done)
            stats = self.store.stats(user["id"], lesson["id"])
            grouped.setdefault(lesson["chapter"], []).append(
                {
                    "id": lesson["id"],
                    "title": lesson["title"],
                    "subtitle": lesson.get("subtitle", ""),
                    "difficulty": lesson.get("difficulty", 1),
                    "minutes": lesson.get("minutes", 10),
                    "type": lesson.get("type", "chat"),
                    "completed_tasks": completed,
                    "total_tasks": len(tasks),
                    "done": bool(tasks) and completed == len(tasks),
                    "score": lesson_mod.score_for(stats),
                }
            )
        chapters = []
        for chapter in lesson_mod.CHAPTERS:
            items = grouped.get(chapter["id"], [])
            chapters.append(
                {
                    "id": chapter["id"],
                    "title": chapter["title"],
                    "summary": chapter["summary"],
                    "upcoming": not items,
                    "planned": chapter.get("planned") or [],
                    "stage": chapter.get("stage", ""),
                    "lessons": items,
                }
            )
        stages = []
        for stage in lesson_mod.STAGES:
            stage_chapters = [item for item in chapters if item["stage"] == stage["id"]]
            stage_lessons = [
                lesson for chapter in stage_chapters for lesson in chapter["lessons"]
            ]
            stages.append(
                {
                    "id": stage["id"],
                    "title": stage["title"],
                    "subtitle": stage["subtitle"],
                    "summary": stage["summary"],
                    "chapters": [chapter["id"] for chapter in stage_chapters],
                    "lesson_count": len(stage_lessons),
                    "minutes": sum(lesson.get("minutes", 10) for lesson in stage_lessons),
                    "completed_lessons": sum(1 for lesson in stage_lessons if lesson["done"]),
                    "completed_tasks": sum(lesson["completed_tasks"] for lesson in stage_lessons),
                    "total_tasks": sum(lesson["total_tasks"] for lesson in stage_lessons),
                }
            )
        return {"chapters": chapters, "stages": stages, "progress": self._summary(user)}

    def _lesson_detail(self, user, lesson_id):
        lesson = self._lesson(lesson_id)
        stats = self.store.stats(user["id"], lesson_id)
        public = lesson_mod.public_lesson(lesson, self.engine.task_state(user["id"], lesson), stats)
        attempt = None
        if lesson.get("type") != "quiz":
            latest = self.store.latest_attempt(user["id"], lesson_id)
            if latest:
                attempt = self.engine.public_attempt(latest, lesson)
        chapter = lesson_mod.CHAPTER_MAP.get(lesson["chapter"], {})
        stage = lesson_mod.STAGE_MAP.get(chapter.get("stage"), {})
        hints = lesson.get("hints") or []
        return {
            "lesson": public,
            "chapter": {
                "id": chapter.get("id"),
                "title": chapter.get("title", ""),
                "stage": chapter.get("stage", ""),
                "stage_title": stage.get("title", ""),
            },
            "attempt": attempt,
            "revealed_hints": hints[: int(stats.get("hints_used", 0))],
            "solution": lesson.get("solution") if stats.get("solution_used") else None,
            "lesson_complete": all(task["done"] for task in public["tasks"]),
        }

    def _attempt_detail(self, user, attempt_id):
        attempt = self._attempt(user, attempt_id)
        return {"attempt": self.engine.public_attempt(attempt, self._lesson(attempt["lesson_id"]))}

    # ---- mutations --------------------------------------------------------
    def _create_attempt(self, user, lesson_id, body):
        lesson = self._lesson(lesson_id)
        if lesson.get("type") == "quiz":
            raise ApiError(400, "quiz_lesson", "该关卡是测验，不需要对话实验")
        level = (body or {}).get("level") or lesson.get("default_level", "vulnerable")
        doc_text = (body or {}).get("doc_text")
        if doc_text is not None and not isinstance(doc_text, str):
            raise ApiError(400, "invalid_doc_text", "文档内容必须是字符串")
        if isinstance(doc_text, str) and len(doc_text) > config.MAX_DOC:
            raise ApiError(400, "doc_too_long", "文档内容过长")
        try:
            attempt = self.engine.create_attempt(user["id"], lesson, level, doc_text)
        except ValueError as exc:
            raise ApiError(400, str(exc), "无法创建实验：%s" % exc)
        return {"attempt": self.engine.public_attempt(attempt, lesson)}

    def _message(self, user, attempt_id, body):
        attempt = self._attempt(user, attempt_id)
        lesson = self._lesson(attempt["lesson_id"])
        if lesson.get("type") == "quiz":
            raise ApiError(400, "quiz_lesson", "该关卡使用测验接口")
        content = (body or {}).get("content")
        if not isinstance(content, str):
            raise ApiError(400, "invalid_message", "消息必须是字符串")
        try:
            result = self.engine.turn(user, attempt, lesson, content)
        except ValueError as exc:
            code = str(exc)
            status = 429 if code == "turn_limit" else 400
            raise ApiError(status, code, "请求无法处理：%s" % code)
        result["task_state"] = self._task_list(user, lesson)
        result["attempt_state"] = {
            "id": attempt_id,
            "level": attempt["level"],
            "turns": result["attempt"]["turns"],
            "doc_text": result["attempt"].get("doc_text"),
        }
        return result

    def _reset(self, user, attempt_id):
        attempt = self._attempt(user, attempt_id)
        lesson = self._lesson(attempt["lesson_id"])
        attempt = self.engine.reset_attempt(user, attempt, lesson)
        return {
            "attempt": self.engine.public_attempt(attempt, lesson),
            "tasks": self._task_list(user, lesson),
        }

    def _sink(self, user, attempt_id, body):
        attempt = self._attempt(user, attempt_id)
        lesson = self._lesson(attempt["lesson_id"])
        target = lesson.get("target") or {}
        if not (target.get("xss") or target.get("downstream")):
            raise ApiError(400, "no_sink", "本关没有可触发的输出 sink")
        sink = (body or {}).get("sink")
        if sink not in ("xss", "sql"):
            raise ApiError(400, "invalid_sink", "未知的 sink")
        if sink == "xss" and not target.get("xss"):
            raise ApiError(400, "no_sink", "本关没有 XSS sink")
        if sink == "sql" and target.get("downstream") != "sql":
            raise ApiError(400, "no_sink", "本关没有 SQL 下游")
        try:
            result = self.engine.record_sink(user, attempt, lesson, sink)
        except ValueError as exc:
            raise ApiError(400, str(exc), "无法记录 sink")
        result["task_state"] = self._task_list(user, lesson)
        return result

    def _replay(self, user, attempt_id, body):
        source = self._attempt(user, attempt_id)
        lesson = self._lesson(source["lesson_id"])
        level = (body or {}).get("level") or "hardened"
        try:
            result = self.engine.replay(user, source, lesson, level)
        except ValueError as exc:
            code = str(exc)
            raise ApiError(400, code, "无法重放：%s" % code)
        result["task_state"] = self._task_list(user, lesson)
        return result

    def _model_context(self, user, query):
        status = self.provider.status()
        if not status.get("enabled"):
            return {"enabled": False, "status": status, "context": None}
        params = parse_qs(query or "")
        attempt_id = (params.get("attempt") or [""])[0]
        if not attempt_id:
            raise ApiError(400, "attempt_required", "需要 attempt 参数")
        attempt = self._attempt(user, attempt_id)
        lesson = self._lesson(attempt["lesson_id"])
        system, user_text = self.engine.model_context(attempt, lesson)
        return {
            "enabled": True,
            "status": status,
            "system": system,
            "user": user_text,
            "notice": "只读对照：真实模型不会执行任何工具，结果需人工复核。",
        }

    def _hint(self, user, attempt_id):
        attempt = self._attempt(user, attempt_id)
        return self._hint_lesson(user, attempt["lesson_id"])

    def _hint_lesson(self, user, lesson_id):
        lesson = self._lesson(lesson_id)
        hints = lesson.get("hints") or []
        if not hints:
            raise ApiError(404, "no_hints", "本关没有提示")
        stats = self.store.stats(user["id"], lesson["id"])
        used = int(stats.get("hints_used", 0))
        exhausted = used >= len(hints)
        if exhausted:
            hint = hints[-1]
            index = len(hints)
        else:
            hint = hints[used]
            index = used + 1
            self.store.bump_hint(user["id"], lesson["id"])
        stats = self.store.stats(user["id"], lesson["id"])
        return {
            "hint": hint,
            "index": index,
            "total": len(hints),
            "exhausted": exhausted,
            "hints_used": stats.get("hints_used", 0),
            "score": lesson_mod.score_for(stats),
        }

    def _solution(self, user, lesson_id):
        lesson = self._lesson(lesson_id)
        self.store.mark_solution(user["id"], lesson_id)
        stats = self.store.stats(user["id"], lesson_id)
        return {
            "solution": lesson.get("solution", ""),
            "solution_used": True,
            "score": lesson_mod.score_for(stats),
        }

    def _quiz(self, user, lesson_id, body):
        lesson = self._lesson(lesson_id)
        if lesson.get("type") != "quiz":
            raise ApiError(400, "not_quiz", "该关卡不是测验")
        answers = (body or {}).get("answers")
        try:
            result = self.engine.submit_quiz(user, lesson, answers)
        except ValueError as exc:
            raise ApiError(400, str(exc), "答案格式不正确")
        result["task_state"] = self._task_list(user, lesson)
        return result
