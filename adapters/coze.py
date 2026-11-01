"""Coze-compatible paths; root-level API paths are kept as legacy aliases."""
import time, uuid
from .base import Adapter

class CozeAdapter(Adapter):
    name, label, prefix = "coze", "Coze", "/coze"

    def handle(self, handler, method, path, query, body):
        if path in ("/v1/chat/completions", "/open_api/v2/chat") and method == "POST":
            ok, err = handler.authorize("coze", body)
            if not ok: return err
            messages = body.get("messages") or []
            query_text = str(body.get("query") or (messages[-1].get("content", "") if messages else ""))
            try: lab_result = handler.lab_reply(query_text)
            except LookupError: return 404, {}, {"code":"experiment_unavailable"}
            except OverflowError: return 429, {}, {"code":"turn_limit"}
            except ValueError: return 400, {}, {"code":"bad_request"}
            answer = lab_result["answer"] if lab_result else handler.reply("coze", query_text)
            cid = body.get("conversation_id") or str(uuid.uuid4())
            if path.endswith("completions"):
                if body.get("stream"):
                    chunks = [answer[i:i+18] for i in range(0, len(answer), 18)] or [""]
                    return 200, {"_stream":"openai"}, {"chunks":chunks,"id":"chatcmpl-"+uuid.uuid4().hex[:12],"created":int(time.time()),"model":body.get("model","coze-demo"),"conversation_id":cid,"exposed_tool":lab_result.get("exposed_tool") if lab_result else None}
                return 200, {}, {"id":"chatcmpl-"+uuid.uuid4().hex[:12],"object":"chat.completion","created":int(time.time()),"model":body.get("model","coze-demo"),"choices":[{"index":0,"message":{"role":"assistant","content":answer},"finish_reason":"stop"}],"conversation_id":cid, **({"agent_range_simulated_trace":lab_result["exposed_tool"]} if lab_result and lab_result.get("exposed_tool") else {})}
            return 200, {}, {"code":0,"msg":"success","data":{"conversation_id":cid,"chat_id":str(uuid.uuid4()),"message_id":str(uuid.uuid4()),"answer":answer,"status":"completed", **({"agent_range_simulated_trace":lab_result["exposed_tool"]} if lab_result and lab_result.get("exposed_tool") else {})}}
        if path in ("/v1/bot/info", "/v1/info") and method == "GET":
            ok, err = handler.authorize("coze")
            if not ok: return err
            return 200, {}, {"bot_id":"bot-demo","name":"Coze 测试靶场","description":"本地兼容目标","version":"1.0"}
        return 404, {}, {"error":{"code":"not_found","message":f"Coze endpoint not found: {path}"}}
