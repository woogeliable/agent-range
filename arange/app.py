"""HTTP transport: sessions, security headers, static files and the JSON API."""
import json
import mimetypes
import os
import re
import sys
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from . import __version__, config
from . import lessons as lesson_mod
from .api import Api, ApiError
from .runtime.engine import Engine
from .runtime.provider import ModelProvider
from .store import Store

BASE_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
    ),
}


def security_headers():
    headers = dict(BASE_SECURITY_HEADERS)
    if config.ALLOW_EMBED:
        headers.pop("X-Frame-Options", None)
        headers["Content-Security-Policy"] = headers["Content-Security-Policy"].replace(
            "frame-ancestors 'none'", "frame-ancestors *"
        )
    return headers


class HttpError(Exception):
    def __init__(self, status, code, message=""):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code


class App:
    def __init__(self, db_path=None, lessons_dir=None, secret=None, web_dir=None):
        self.store = Store(db_path or config.DB_PATH)
        self.lessons = lesson_mod.load(lessons_dir or str(config.LESSONS_DIR))
        self.secret = secret or config.instance_secret()
        self.web_dir = str(web_dir or config.WEB_DIR)
        self.provider = ModelProvider()
        self.engine = Engine(self.store, self.lessons, self.secret)
        self.api = Api(self.store, self.engine, self.lessons, self.provider, __version__)

    def cleanup(self):
        self.store.purge_expired()


class RangeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AgentRange/3.1"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    @property
    def app(self):
        return self.server.app

    # ---- verbs ------------------------------------------------------------
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_HEAD(self):
        self._dispatch("GET")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        for key, value in security_headers().items():
            self.send_header(key, value)
        self.end_headers()

    # ---- dispatch ---------------------------------------------------------
    def _dispatch(self, method):
        parsed = urlsplit(self.path)
        path = parsed.path
        try:
            body = self._read_body() if method == "POST" else {}
            if method == "POST" and self.headers.get("X-AR-CSRF") != "1":
                raise HttpError(403, "csrf_required", "缺少 CSRF 头")

            needs_session = path == "/" or path.startswith("/lesson/") or path.startswith("/api/")
            user = None
            new_token = None
            if needs_session:
                user, new_token = self._session()

            if path.startswith("/api/"):
                if user is None:
                    raise HttpError(401, "session_required", "会话无效")
                status, payload = self.app.api.handle(method, path, parsed.query, body, user)
                self._json(status, payload, new_token)
                return

            if method != "GET":
                raise HttpError(405, "method_not_allowed", "方法不允许")

            if path == "/" or re.match(r"^/lesson/[A-Za-z0-9._\-]+$", path):
                self._page(new_token)
                return

            if path.startswith("/static/"):
                self._static(path[len("/static/"):], new_token)
                return

            if path == "/favicon.ico":
                self._empty(204, new_token)
                return

            raise HttpError(404, "not_found", "页面不存在")

        except ApiError as exc:
            self._json(exc.status, {"error": exc.code, "message": exc.message}, None)
        except HttpError as exc:
            if exc.status == 413:
                self.close_connection = True
            self._json(exc.status, {"error": exc.code, "message": exc.message}, None)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            traceback.print_exc(file=sys.stderr)
            try:
                self._json(500, {"error": "internal_error", "message": "服务器内部错误"}, None)
            except Exception:
                self.close_connection = True

    # ---- session & body ---------------------------------------------------
    def _session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            cookie = SimpleCookie()
        token = ""
        if config.SESSION_COOKIE in cookie:
            token = cookie[config.SESSION_COOKIE].value
        user = self.app.store.user_for_session(token)
        if user:
            return user, None
        user = self.app.store.create_user("guest")
        token = self.app.store.create_session(user["id"])
        return user, token

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            raise HttpError(400, "invalid_length", "Content-Length 无效")
        if length < 0:
            raise HttpError(400, "invalid_length", "Content-Length 无效")
        if length > config.MAX_BODY:
            raise HttpError(413, "request_too_large", "请求体过大")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise HttpError(400, "invalid_json", "请求体必须是 JSON")
        if not isinstance(payload, dict):
            raise HttpError(400, "invalid_json", "请求体必须是 JSON 对象")
        return payload

    # ---- responses --------------------------------------------------------
    def _base_headers(self, content_type, length, cache, token):
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(length),
            "Cache-Control": cache,
        }
        headers.update(security_headers())
        if token:
            if config.ALLOW_EMBED:
                # Preview proxies frame the UI cross-site; Lax cookies would be
                # dropped in a third-party context. The preview is HTTPS.
                cookie = "%s=%s; Path=/; HttpOnly; SameSite=None; Secure; Max-Age=%d"
            else:
                cookie = "%s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d"
            headers["Set-Cookie"] = cookie % (config.SESSION_COOKIE, token, config.SESSION_TTL)
        return headers

    def _send(self, status, body, content_type, cache="no-store", token=None):
        headers = self._base_headers(content_type, len(body), cache, token)
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _empty(self, status, token=None):
        headers = self._base_headers("text/plain; charset=utf-8", 0, "no-store", token)
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()

    def _json(self, status, payload, token):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, raw, "application/json; charset=utf-8", "no-store", token)

    def _page(self, token):
        path = os.path.join(self.app.web_dir, "index.html")
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
        except OSError:
            raise HttpError(500, "ui_missing", "界面文件缺失")
        self._send(200, raw, "text/html; charset=utf-8", "no-store", token)

    def _static(self, relative, token):
        safe = relative.replace("\\", "/")
        if safe.startswith("/") or ".." in safe.split("/"):
            raise HttpError(404, "not_found", "资源不存在")
        base = os.path.abspath(self.app.web_dir)
        target = os.path.abspath(os.path.join(base, safe))
        if os.path.commonpath([base, target]) != base or not os.path.isfile(target):
            raise HttpError(404, "not_found", "资源不存在")
        with open(target, "rb") as handle:
            raw = handle.read()
        content_type = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in (
            "application/javascript",
            "application/json",
            "image/svg+xml",
        ):
            content_type += "; charset=utf-8"
        self._send(200, raw, content_type, "public, max-age=60", token)


def make_server(host, port, app):
    httpd = ThreadingHTTPServer((host, port), RangeHandler)
    httpd.app = app
    httpd.daemon_threads = True
    return httpd
