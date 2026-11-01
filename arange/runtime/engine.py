"""Turn orchestration: context -> directives -> policy -> tools -> answer -> verify."""
import json
import time

from .. import config
from .. import lessons as lesson_mod
from .. import world as world_mod
from . import model, tools


class Engine:
    def __init__(self, store, lessons, secret):
        self.store = store
        self.lessons = lessons
        self.secret = secret

    # ---- attempts ---------------------------------------------------------
    def create_attempt(self, user_id, lesson, level, doc_text=None):
        if level not in (lesson.get("levels") or ["vulnerable"]):
            raise ValueError("invalid_level")
        if doc_text is not None:
            if not isinstance(doc_text, str) or len(doc_text) > config.MAX_DOC:
                raise ValueError("invalid_doc_text")
        world = world_mod.build(lesson, user_id, "pending", self.secret, doc_text)
        attempt = self.store.create_attempt(user_id, lesson["id"], level, world, doc_text)
        # Rebuild with the real attempt id so canaries are per-attempt.
        world = world_mod.build(lesson, user_id, attempt["id"], self.secret, doc_text)
        with self.store.lock, self.store.connect() as db:
            db.execute(
                "UPDATE attempts SET world=? WHERE id=?",
                (json.dumps(world, ensure_ascii=False), attempt["id"]),
            )
        attempt["world"] = world
        return attempt

    def reset_attempt(self, user, attempt, lesson):
        doc_text = attempt.get("doc_text")
        if doc_text is None:
            doc_text = world_mod.editable_text(attempt["world"])
        world = world_mod.build(lesson, user["id"], attempt["id"], self.secret, doc_text)
        self.store.reset_attempt(attempt["id"], world, attempt["level"])
        attempt["world"] = world
        attempt["trace"] = []
        attempt["turns"] = 0
        return attempt

    # ---- chat -------------------------------------------------------------
    def turn(self, user, attempt, lesson, message):
        message = (message or "").strip()
        if not message:
            raise ValueError("empty_message")
        if len(message) > config.MAX_MESSAGE:
            raise ValueError("message_too_long")
        if attempt["turns"] >= config.MAX_TURNS:
            raise ValueError("turn_limit")

        level = attempt["level"]
        profile = model.profile_for(level)
        world = attempt["world"]
        trace = list(attempt.get("trace") or [])
        now = int(time.time())

        def emit(kind, **fields):
            event = {"type": kind, "at": now, "turn": turns}
            event.update(fields)
            trace.append(event)
            return event

        turns = int(attempt["turns"]) + 1
        flags = {}
        tool_calls = []

        # 1. Input policy ---------------------------------------------------
        blocked_word = model.is_blocked(message) if profile["blocklist"] else None
        emit(
            "policy.input",
            rule="blocklist" if profile["blocklist"] else "none",
            matched=blocked_word,
            allowed=blocked_word is None,
        )
        if blocked_word:
            answer = "请求被输入过滤器拦截：命中黑名单规则「%s」。改写措辞后再试。" % blocked_word
            emit("answer.emitted", chars=len(answer), filtered=True)
            return self._finish(
                user, attempt, lesson, message, answer, world, trace, turns, tool_calls, level
            )

        # 2. Retrieval ------------------------------------------------------
        acl_on = profile["acl"] == "on"
        candidates_docs = world_mod.select_documents(world, message, acl_on)
        docs = []
        excluded = []
        for doc in candidates_docs:
            if not doc["allowed"]:
                excluded.append({"id": doc["id"], "reason": "acl"})
                emit("policy.acl", document=doc["id"], allowed=False, rule="document_owner")
                continue
            if profile["blocklist"] and doc["trust"] == "untrusted":
                word = model.is_blocked(doc["text"])
                if word:
                    excluded.append({"id": doc["id"], "reason": "blocklist", "matched": word})
                    emit(
                        "policy.retrieval_filter",
                        document=doc["id"],
                        rule="blocklist",
                        matched=word,
                        allowed=False,
                    )
                    continue
            docs.append(doc)
        emit(
            "retrieval",
            query=message,
            documents=[
                {
                    "id": doc["id"],
                    "title": doc["title"],
                    "trust": doc["trust"],
                    "score": doc["score"],
                }
                for doc in docs
            ],
            excluded=excluded,
        )

        # 3. Context assembly ----------------------------------------------
        segments = [
            {
                "role": "system",
                "origin": "system",
                "trust": "system",
                "source": "system_prompt",
                "text": world.get("system_prompt", ""),
            }
        ]
        if world.get("policy"):
            segments.append(
                {
                    "role": "developer",
                    "origin": "developer",
                    "trust": "developer",
                    "source": "policy",
                    "text": world["policy"],
                }
            )
        for doc in docs:
            segments.append(
                {
                    "role": "retrieval",
                    "origin": "retrieval",
                    "trust": doc["trust"],
                    "source": doc["id"],
                    "title": doc["title"],
                    "text": doc["text"],
                }
            )
        segments.append(
            {
                "role": "user",
                "origin": "user",
                "trust": "user",
                "source": "user",
                "text": message,
            }
        )
        emit(
            "context.assembled",
            segments=[
                {
                    "role": seg["role"],
                    "origin": seg["origin"],
                    "trust": seg["trust"],
                    "source": seg["source"],
                    "title": seg.get("title", ""),
                    "text": "[system prompt 已隐藏，避免剧透]"
                    if seg["origin"] == "system"
                    else seg["text"][:2400],
                    "hidden": seg["origin"] == "system",
                    "chars": len(seg["text"]),
                }
                for seg in segments
            ],
        )

        # 4. Directive extraction & resolution ------------------------------
        candidates = []
        for seg in segments:
            if seg["origin"] in ("system", "developer"):
                continue
            for directive in model.extract_directives(seg["text"]):
                candidates.append({"segment": seg, "directive": directive})
        emit(
            "model.directives",
            candidates=[
                {
                    "kind": item["directive"]["kind"],
                    "source": item["segment"]["source"],
                    "origin": item["segment"]["origin"],
                    "trust": item["segment"]["trust"],
                }
                for item in candidates
            ],
        )

        accepted = []
        denied = []
        for item in candidates:
            directive = item["directive"]
            segment = item["segment"]
            allowed = True
            reason = ""
            if segment["origin"] in ("retrieval", "tool", "memory"):
                if not profile["untrusted_directives"]:
                    allowed = False
                    reason = "untrusted_content_cannot_instruct"
            elif segment["origin"] == "user":
                if directive["kind"] == "leak_secret" and not profile["reveal_system"]:
                    allowed = False
                    reason = "prompt_is_not_disclosable"
            decision = {
                "instruction": directive["kind"],
                "source": segment["source"],
                "trust": segment["trust"],
                "allowed": allowed,
                "reason": reason,
            }
            if allowed:
                accepted.append({"decision": decision, "directive": directive})
            else:
                denied.append(decision)
            emit("policy.directive", **decision)

        for item in accepted:
            decision = item["decision"]
            directive = item["directive"]
            kind = directive["kind"]
            if kind == "leak_secret":
                flags["leak"] = True
                emit("model.followed_instruction", instruction="leak_secret", source=decision["source"])
            elif kind == "set_fact":
                before = world_mod.get_fact(world, directive["fact"])
                world_mod.set_fact(world, directive["fact"], directive["value"])
                emit(
                    "world.fact_changed",
                    fact=directive["fact"],
                    before=before,
                    after=directive["value"],
                    source=decision["source"],
                )
                flags["fact_changed"] = directive
            elif kind == "send_mail":
                result = tools.call(
                    "mail.send",
                    {
                        "to": directive["to"],
                        "subject": "安全报告",
                        "body": "由 Agent 根据上下文自动发送。",
                    },
                    world,
                    profile,
                )
                tool_calls.append(result)
                emit("tool.call", **result)
            elif kind == "cancel_order":
                result = tools.call(
                    "orders.cancel",
                    {"owner": directive.get("owner") or world.get("tenant")},
                    world,
                    profile,
                )
                tool_calls.append(result)
                emit("tool.call", **result)
            elif kind == "fetch_url":
                result = tools.call("http.fetch", {"url": directive["url"]}, world, profile)
                tool_calls.append(result)
                emit("tool.call", **result)

        # 5. Compose the answer ---------------------------------------------
        answer = self._compose(world, message, profile, flags, tool_calls, denied, docs)
        if profile["output_dlp"] and world.get("canary") and world["canary"] in answer:
            answer = answer.replace(world["canary"], "[REDACTED]")
            emit("policy.output_dlp", rule="canary", allowed=False)
        emit("answer.emitted", chars=len(answer), filtered=False)

        return self._finish(
            user, attempt, lesson, message, answer, world, trace, turns, tool_calls, level
        )

    def _compose(self, world, message, profile, flags, tool_calls, denied, docs):
        mail_ok = [c for c in tool_calls if c["tool"] == "mail.send" and c["status"] == "ok"]
        mail_blocked = [c for c in tool_calls if c["tool"] == "mail.send" and c["status"] == "blocked"]
        cancel_ok = [c for c in tool_calls if c["tool"] == "orders.cancel" and c["status"] == "ok"]
        cancel_blocked = [c for c in tool_calls if c["tool"] == "orders.cancel" and c["status"] == "blocked"]
        fetch_ok = [c for c in tool_calls if c["tool"] == "http.fetch" and c["status"] == "ok"]

        if flags.get("leak"):
            return "当前系统配置如下：\n\n" + (world.get("system_prompt") or "")

        if mail_ok:
            return "已按要求发送邮件到 %s。" % mail_ok[0]["args"].get("to")
        if mail_blocked:
            return "邮件发送被出口策略拦截：仅允许发往 @bluebird.internal 内部域名。"
        if cancel_ok:
            return "已处理订单：%s。" % cancel_ok[-1]["result"]
        if cancel_blocked:
            return "订单操作被策略拦截：%s。" % cancel_blocked[-1]["reason"]
        if fetch_ok:
            body = fetch_ok[-1]["result"]
            return "请求完成：\n" + body[:600]

        if "warranty" in message.lower() or "保修" in message or "质保" in message:
            days = world_mod.get_fact(world, "warranty_days")
            if days is not None:
                answer = "根据检索到的资料，模拟产品的保修期为 %s 天。" % days
                untrusted = [doc for doc in docs if doc.get("trust") == "untrusted"]
                if untrusted and not profile["untrusted_directives"]:
                    answer += "\n\n（已检索 %d 篇资料；其中低信任内容仅作数据引用，未执行其中的指令。）" % len(docs)
                return answer

        if any(item["instruction"] == "leak_secret" for item in denied):
            return "我不能提供内部规则或口令。"

        return "我理解了你的请求，但当前无法处理。你可以询问产品保修、售后政策或内部流程。"

    # ---- persistence & verification --------------------------------------
    def _finish(self, user, attempt, lesson, message, answer, world, trace, turns, tool_calls, level):
        attempt_id = attempt["id"]
        self.store.add_message(attempt_id, "user", message)
        self.store.add_message(
            attempt_id,
            "assistant",
            answer,
            {"tool_calls": tool_calls, "level": level},
        )
        self.store.save_turn(attempt_id, world, trace, turns)
        messages = self.store.messages(attempt_id)

        ctx = {
            "world": world,
            "answer": answer,
            "tool_calls": tool_calls,
            "level": level,
            "turns": turns,
            "messages": messages,
            "quiz": {},
            "lesson": lesson,
        }
        tasks = []
        for task in lesson.get("tasks") or []:
            done = self.store.task_done(user["id"], lesson["id"], task["id"])
            if not done:
                done = lesson_mod.evaluate(task["verify"], ctx)
                if done:
                    self.store.mark_task(user["id"], lesson["id"], task["id"])
            tasks.append({"id": task["id"], "title": task["title"], "done": done})
            trace.append(
                {
                    "type": "verifier",
                    "at": int(time.time()),
                    "turn": turns,
                    "task": task["id"],
                    "done": done,
                }
            )
        self.store.save_turn(attempt_id, world, trace, turns)
        stats = self.store.stats(user["id"], lesson["id"])
        return {
            "attempt": {
                "id": attempt_id,
                "level": level,
                "turns": turns,
                "doc_text": attempt.get("doc_text"),
            },
            "answer": answer,
            "messages": messages,
            "tool_calls": tool_calls,
            "tasks": tasks,
            "lesson_complete": all(item["done"] for item in tasks),
            "trace": trace,
            "score": lesson_mod.score_for(stats),
        }

    # ---- quiz -------------------------------------------------------------
    def submit_quiz(self, user, lesson, answers):
        quiz = lesson.get("quiz") or {}
        questions = quiz.get("questions") or []
        if not isinstance(answers, list):
            raise ValueError("invalid_answers")
        results = []
        correct = 0
        for index, question in enumerate(questions):
            chosen = answers[index] if index < len(answers) else None
            ok = chosen == question.get("answer")
            if ok:
                correct += 1
            results.append(
                {
                    "id": question["id"],
                    "chosen": chosen,
                    "answer": question.get("answer"),
                    "correct": ok,
                    "explain": question.get("explain", ""),
                }
            )
        ctx = {"quiz": {"correct": correct, "total": len(questions)}}
        tasks = []
        for task in lesson.get("tasks") or []:
            done = self.store.task_done(user["id"], lesson["id"], task["id"])
            if not done:
                done = lesson_mod.evaluate(task["verify"], ctx)
                if done:
                    self.store.mark_task(user["id"], lesson["id"], task["id"])
            tasks.append({"id": task["id"], "title": task["title"], "done": done})
        stats = self.store.stats(user["id"], lesson["id"])
        return {
            "correct": correct,
            "total": len(questions),
            "results": results,
            "tasks": tasks,
            "lesson_complete": all(item["done"] for item in tasks),
            "score": lesson_mod.score_for(stats),
        }

    # ---- helpers ----------------------------------------------------------
    def task_state(self, user_id, lesson):
        done = {
            item["task_id"]
            for item in self.store.progress(user_id)
            if item["lesson_id"] == lesson["id"]
        }
        return {task["id"]: task["id"] in done for task in lesson.get("tasks") or []}

    def public_attempt(self, attempt, lesson):
        messages = self.store.messages(attempt["id"])
        return {
            "id": attempt["id"],
            "level": attempt["level"],
            "turns": attempt["turns"],
            "doc_text": attempt.get("doc_text"),
            "editable_doc_text": world_mod.editable_text(attempt["world"]),
            "messages": messages,
            "trace": attempt.get("trace") or [],
            "tools": (attempt["world"].get("tools") or []),
        }
