"""Generic HTTP target: health, echo, and deterministic mock response."""
from .base import Adapter

class HttpAdapter(Adapter):
    name, label, prefix = "http", "HTTP", "/http"

    def handle(self, handler, method, path, query, body):
        if path in ("", "/", "/health") and method == "GET":
            return 200, {}, {"ok":True,"service":"agent-range-http","platform":"http"}
        ok, err = handler.authorize("http", body)
        if not ok: return err
        if method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            return 200, {}, {"ok":True,"target":"agent-range","platform":"http","method":method,"path":path or "/","query":query,"received":body,"note":"这是本地回显目标；不会向外部网络转发。"}
        return 405, {}, {"error":"method_not_allowed"}
