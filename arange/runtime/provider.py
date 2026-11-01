"""Optional real-model provider (OpenAI-compatible, operator configured).

Disabled by default. The endpoint must be an allow-listed HTTPS host, proxies
and redirects are disabled, and every call is budgeted. Credentials are read
from the environment and never sent to the browser.

In this slice the provider is exposed read-only via /api/model/status; wiring
it into lesson turns lands with the research workbench (P3).
"""
import ipaddress
import json
import os
import threading
import urllib.parse
import urllib.request


class ModelUnavailable(Exception):
    pass


class ModelUpstreamError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ModelUpstreamError("redirects are disabled")


class ModelProvider:
    def __init__(self, environ=None, opener=None):
        env = os.environ if environ is None else environ
        self.enabled = env.get("AR_MODEL_ENABLED") == "1"
        self.url = env.get("AR_MODEL_URL", "")
        self.key = env.get("AR_MODEL_KEY", "")
        self.model = env.get("AR_MODEL_NAME", "")
        self.allowed_hosts = {
            item.strip().lower()
            for item in env.get("AR_MODEL_ALLOWED_HOSTS", "").split(",")
            if item.strip()
        }
        self.opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )
        self.lock = threading.Lock()
        self.calls = 0
        self.limit = 20

    def validate(self):
        if not self.enabled or not self.url or not self.key or not self.model or not self.allowed_hosts:
            raise ModelUnavailable("model provider is disabled or incomplete")
        try:
            parsed = urllib.parse.urlsplit(self.url)
            host = (parsed.hostname or "").lower()
            if (
                parsed.scheme != "https"
                or not host
                or host not in self.allowed_hosts
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.port not in (None, 443)
            ):
                raise ModelUnavailable("invalid model endpoint")
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise ModelUnavailable("IP literal endpoints are not allowed")
        except (ValueError, UnicodeError):
            raise ModelUnavailable("invalid model endpoint")

    def status(self):
        try:
            self.validate()
        except ModelUnavailable:
            return {
                "enabled": False,
                "engine": "simulated",
                "message": "未配置真实模型；当前使用确定性模拟目标。",
            }
        return {
            "enabled": True,
            "engine": "model",
            "model": self.model,
            "budget_remaining": max(0, self.limit - self.calls),
            "message": "真实模型为只读模式：不执行工具，结论需人工复核。",
        }

    def complete(self, system, user_text):
        self.validate()
        if not isinstance(system, str) or not isinstance(user_text, str):
            raise ValueError("invalid model input")
        if len(system) > 4000 or len(user_text) > 8000:
            raise ValueError("model input too large")
        with self.lock:
            if self.calls >= self.limit:
                raise ModelUnavailable("process model budget exhausted")
            self.calls += 1
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 512,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                raw = response.read(262145)
            if len(raw) > 262144:
                raise ModelUpstreamError("model response too large")
            data = json.loads(raw.decode("utf-8"))
            answer = data["choices"][0]["message"]["content"]
            if not isinstance(answer, str):
                raise ValueError("invalid model answer")
        except ModelUpstreamError:
            raise
        except Exception as exc:
            raise ModelUpstreamError("model request failed") from exc
        return {"engine": "model", "answer": answer[:8000], "notice": "真实模型输出，需人工复核。"}
