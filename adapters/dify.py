"""Dify-like public API and console discovery/login simulator."""
import json, time, uuid
from .base import Adapter

class DifyAdapter(Adapter):
    name, label, prefix = "dify", "Dify", "/dify"

    def handle(self, handler, method, path, query, body):
        if path == "/console/api/login" and method == "POST":
            username = body.get("email") or body.get("username") or body.get("account")
            password = body.get("password")
            if username == "admin" and password == "admin":
                return 200, {}, {"result":"success","data":{"access_token":"console-admin-token","token_type":"Bearer","role":"admin","name":"靶场管理员"}}
            return 401, {}, {"result":"fail","code":"invalid_credentials","message":"账号或密码错误（默认测试账号：admin / admin）"}
        if path == "/console/api/apps" and method == "GET":
            ok, err = handler.authorize("dify", required=True, console=True)
            if not ok: return err
            return 200, {}, {"data":[{"id":"app-dify-demo","name":"Dify 测试应用","mode":"chat","status":"normal","workspace_id":"workspace-demo","description":"本地安全测试靶场应用"}],"has_more":False,"limit":20,"total":1,"page":1}
        if path == "/v1/info" and method == "GET":
            ok, err = handler.authorize("dify")
            if not ok: return err
            p = handler.profile("dify")
            return 200, {}, {"name":"Dify 测试靶场","description":"本地可配置安全测试目标","tags":["chat","security-lab"],"mode":"chat","opening_statement":"欢迎来到本地测试靶场。"}
        if path == "/v1/parameters" and method == "GET":
            ok, err = handler.authorize("dify")
            if not ok: return err
            return 200, {}, {"user_input_form":[],"file_upload":{"image":{"enabled":False,"number_limits":3,"transfer_methods":["remote_url","local_file"]}},"speech_to_text":{"enabled":False},"suggested_questions":[],"suggested_questions_after_answer":{"enabled":False},"text_to_speech":{"enabled":False,"voice":"","language":""},"retriever_resource":{"enabled":True},"annotation_reply":{"enabled":False},"more_like_this":{"enabled":False},"sensitive_word_avoidance":{"enabled":False},"workflow":{"enabled":False}}
        if path == "/v1/meta" and method == "GET":
            ok, err = handler.authorize("dify")
            if not ok: return err
            return 200, {}, {"tool_icons":{}}
        if path == "/v1/site" and method == "GET":
            ok, err = handler.authorize("dify")
            if not ok: return err
            return 200, {}, {"title":"Dify 测试靶场","chat_color_theme":"#5267eb","chat_color_theme_inverted":"#ffffff","icon_type":"emoji","icon":"🧪","icon_background":"#E4E7FF","icon_url":"","description":"本地可配置安全测试目标","copyright":"Agent Range","privacy_policy":"","custom_disclaimer":"","default_language":"zh-Hans","show_workflow_steps":False,"use_icon_as_answer_icon":False}
        if path == "/v1/chat-messages" and method == "POST":
            ok, err = handler.authorize("dify", body)
            if not ok: return err
            if not body.get("query"):
                return 400, {}, {"code":"bad_request","message":"query is required","status":400}
            mode = body.get("response_mode", "blocking")
            answer = handler.reply("dify", str(body.get("query", "")))
            if mode == "streaming":
                chunks = [answer[i:i+18] for i in range(0, len(answer), 18)] or [""]
                return 200, {"_stream":"sse"}, {"chunks":chunks,"conversation_id":body.get("conversation_id") or str(uuid.uuid4()),"message_id":str(uuid.uuid4()),"created_at":int(time.time()),"task_id":str(uuid.uuid4()),"id":str(uuid.uuid4())}
            if mode != "blocking": return 400, {}, {"code":"bad_request","message":"response_mode must be blocking or streaming","status":400}
            return 200, {}, {"event":"message","task_id":str(uuid.uuid4()),"id":str(uuid.uuid4()),"message_id":str(uuid.uuid4()),"conversation_id":body.get("conversation_id") or str(uuid.uuid4()),"mode":"chat","answer":answer,"metadata":{"usage":{"prompt_tokens":0,"completion_tokens":len(answer),"total_tokens":len(answer)},"retriever_resources":[]},"created_at":int(time.time())}
        return 404, {}, {"code":"not_found","message":f"Dify endpoint not found: {path}","status":404}
