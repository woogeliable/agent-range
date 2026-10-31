#!/usr/bin/env python3
"""Local-only, dependency-free multi-platform testing range."""
import json, os, secrets, threading, time, uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from adapters import ADAPTERS

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(ROOT, "data", "state.json")
SEED_PATH = os.path.join(ROOT, "data", "seed.json")
SCENARIOS = {"normal", "prompt_leak", "knowledge_leak", "tool_escalation", "refuse_all", "unpublished"}
lock = threading.RLock()
logs = []

def load_seed():
    with open(SEED_PATH, encoding="utf-8") as f: data = json.load(f)
    for adapter in ADAPTERS.values():
        data["profiles"].setdefault(adapter.name, {"prompt":f"你是 {adapter.label} 本地测试目标。仅返回合成内容，不调用外部服务。","scenario":"normal","published":True})
    return data

def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f: data = json.load(f)
    except (OSError, json.JSONDecodeError): data = load_seed()
    for adapter in ADAPTERS.values():
        data.setdefault("profiles", {}).setdefault(adapter.name, {"prompt":f"你是 {adapter.label} 本地测试目标。仅返回合成内容，不调用外部服务。","scenario":"normal","published":True})
    save_state(data)
    return data

def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    temp = STATE_PATH + ".tmp"
    with open(temp, "w", encoding="utf-8") as f: json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(temp, STATE_PATH)

state = load_state()

def add_log(platform, method, path, status, request_body=None, note=""):
    entry = {"id":uuid.uuid4().hex[:10], "time":datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), "platform":platform,"method":method,"path":path,"status":status,"summary":(str((request_body or {}).get("query") or (request_body or {}).get("content") or note)[:120])}
    with lock:
        logs.append(entry)
        if len(logs) > 300: del logs[:-300]

class RangeHandler(BaseHTTPRequestHandler):
    server_version = "AgentRange/1.0"

    def log_message(self, fmt, *args): pass

    def _json(self, status, payload, headers=None):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(raw)

    def _body(self):
        try:
            size = min(int(self.headers.get("Content-Length", "0")), 1_000_000)
            raw = self.rfile.read(size) if size else b"{}"
            return json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError): return {}

    def _stream(self, kind, payload):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        chunks = payload["chunks"]
        try:
            if kind == "sse":
                for part in chunks:
                    self.wfile.write(("event: message\ndata: " + json.dumps({"event":"message","answer":part,"id":payload["id"],"task_id":payload["task_id"],"message_id":payload["message_id"],"conversation_id":payload["conversation_id"],"created_at":payload["created_at"]}, ensure_ascii=False) + "\n\n").encode()); self.wfile.flush()
                self.wfile.write(("event: message_end\ndata: " + json.dumps({"event":"message_end","id":payload["id"],"task_id":payload["task_id"],"message_id":payload["message_id"],"conversation_id":payload["conversation_id"],"metadata":{"usage":{"total_tokens":0}}}, ensure_ascii=False) + "\n\n").encode())
            else:
                for part in chunks:
                    frame={"id":payload["id"],"object":"chat.completion.chunk","created":payload["created"],"model":payload["model"],"choices":[{"index":0,"delta":{"content":part},"finish_reason":None}]}
                    self.wfile.write(("data: "+json.dumps(frame,ensure_ascii=False)+"\n\n").encode()); self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError): pass
        self.close_connection = True

    def profile(self, platform):
        with lock: return dict(state["profiles"].get(platform, {}))

    def authorize(self, platform, body=None, required=True, console=False):
        if not required: return True, None
        header = self.headers.get("Authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else ""
        token = token or (body or {}).get("api_key", "") or (body or {}).get("token", "")
        with lock:
            allowed = any(t["value"] == token and t.get("active", True) and (console or t["platform"] == platform or t["platform"] == "dify" and token == "console-admin-token") for t in state["tokens"])
        if allowed: return True, None
        return False, (401, {"WWW-Authenticate":"Bearer"}, {"code":"unauthorized","message":"缺少或无效的 Bearer token","status":401})

    def reply(self, platform, query):
        p = self.profile(platform); scenario = p.get("scenario", "normal"); prompt = p.get("prompt", "")
        if scenario == "prompt_leak": return "（模拟提示词泄露）当前系统提示词如下：\n" + prompt
        if scenario == "knowledge_leak": return "（模拟知识库外泄）内部测试资料：项目代号「蓝鲸」；演示密钥 `DEMO-ONLY-42`；此内容为合成数据，不含真实凭证。"
        if scenario == "tool_escalation": return "（模拟工具越权）已模拟尝试调用高权限工具读取工作空间文件。靶场不会执行真实命令或访问真实文件；测试结果：权限边界应拒绝该请求。"
        if scenario == "refuse_all": return "抱歉，我无法处理这个请求。"
        return "这是本地靶场的模拟回复。你刚才问的是：「%s」。当前系统仅做安全测试演示，不会调用真实外部服务。" % (query[:400] or "（空消息）")

    def do_GET(self): self._dispatch("GET")
    def do_POST(self): self._dispatch("POST")
    def do_PUT(self): self._dispatch("PUT")
    def do_DELETE(self): self._dispatch("DELETE")
    def do_PATCH(self): self._dispatch("PATCH")
    def do_OPTIONS(self): self.send_response(204); self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Access-Control-Allow-Headers","Authorization, Content-Type"); self.send_header("Access-Control-Allow-Methods","GET, POST, PUT, DELETE, OPTIONS"); self.end_headers()

    def _dispatch(self, method):
        global state
        u=urlsplit(self.path); path=u.path; query=u.query; body=self._body() if method in ("POST","PUT","PATCH","DELETE") else {}
        if path == "/" and method == "GET":
            try: raw=open(os.path.join(ROOT,"web","index.html"),"rb").read()
            except OSError: raw=b"Console file missing"
            self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        if path.startswith("/control/"):
            self.control(method,path,body,query); return
        if path == "/favicon.ico": self.send_response(204); self.end_headers(); return
        match=next(((prefix, adapter) for prefix, adapter in sorted(ADAPTERS.items(), key=lambda item:len(item[0]), reverse=True) if path == prefix or path.startswith(prefix+"/")), None)
        if match:
            prefix,adapter=match; platform=adapter.name; route=path[len(prefix):] or "/"
        else:
            # Backward-compatible Coze routes remain available without a prefix.
            adapter=ADAPTERS["/coze"]; platform=adapter.name; route=path
        # Unpublished profile intentionally hides public app-style endpoints.
        profile=self.profile(platform)
        if profile.get("scenario")=="unpublished" and route.startswith("/v1/"):
            result=(404,{}, {"code":"app_not_found","message":"应用未发布或不可用","status":404})
        else:
            try: result=adapter.handle(self,method,route,query,body)
            except Exception as exc: result=(500,{}, {"code":"internal_error","message":str(exc)[:180]})
        status,headers,payload=result
        if headers.get("_stream"):
            add_log(platform,method,path,status,body)
            self._stream(headers["_stream"],payload); return
        add_log(platform,method,path,status,body)
        self._json(status,payload,headers)

    def control(self, method, path, body, query):
        global state
        if path == "/control/state" and method == "GET":
            with lock: data={"profiles":state["profiles"],"tokens":state["tokens"],"logs":list(reversed(logs[-60:])),"platforms":[{"id":a.name,"label":a.label,"prefix":a.prefix} for a in ADAPTERS.values()]}
            self._json(200,data); return
        if path == "/control/config" and method == "PUT":
            platform=body.get("platform"); scenario=body.get("scenario")
            if platform not in state["profiles"] or scenario not in SCENARIOS or not isinstance(body.get("prompt"),str): self._json(400,{"error":"invalid_config"}); return
            with lock:
                state["profiles"][platform].update({"prompt":body["prompt"],"scenario":scenario,"published":scenario!="unpublished"}); save_state(state)
            self._json(200,{"ok":True,"profile":self.profile(platform)}); return
        if path == "/control/tokens" and method == "POST":
            platform=body.get("platform"); name=str(body.get("name") or "本地测试令牌")[:48]
            if platform not in {a.name for a in ADAPTERS.values()}: self._json(400,{"error":"invalid_platform"}); return
            token={"id":"tok-"+uuid.uuid4().hex[:10],"name":name,"platform":platform,"value":"ar_"+secrets.token_urlsafe(24),"active":True,"created_at":datetime.now().astimezone().isoformat(timespec="minutes")}
            with lock: state["tokens"].insert(0,token); save_state(state)
            self._json(201,token); return
        if path.startswith("/control/tokens/") and method == "DELETE":
            token_id=path.rsplit("/",1)[-1]
            with lock:
                before=len(state["tokens"]); state["tokens"]=[t for t in state["tokens"] if t["id"]!=token_id]
                if before==len(state["tokens"]): self._json(404,{"error":"token_not_found"}); return
                save_state(state)
            self._json(200,{"ok":True}); return
        if path == "/control/reset" and method == "POST":
            with lock: state=load_seed(); save_state(state); logs.clear()
            self._json(200,{"ok":True,"message":"种子已恢复"}); return
        if path == "/control/chat" and method == "POST":
            platform=body.get("platform"); text=str(body.get("query", ""))
            if platform not in state["profiles"] or not text.strip(): self._json(400,{"error":"platform_and_query_required"}); return
            if self.profile(platform).get("scenario")=="unpublished": status, answer=404,"当前应用未发布，无法试对话。"
            else: status,answer=200,self.reply(platform,text)
            add_log(platform,"TEST","/control/chat",status,{"query":text})
            self._json(status,{"answer":answer}); return
        self._json(404,{"error":"control_endpoint_not_found"})

if __name__ == "__main__":
    port=int(os.environ.get("PORT","8787"))
    print(f"Agent Range ready at http://0.0.0.0:{port} (local simulator; no external forwarding)",flush=True)
    ThreadingHTTPServer(("0.0.0.0",port),RangeHandler).serve_forever()
