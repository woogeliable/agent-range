import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import server

class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.RangeHandler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.http.server_port}"

    @classmethod
    def tearDownClass(cls):
        req = urllib.request.Request(cls.base + "/control/reset", data=b"{}", method="POST", headers={"Content-Type":"application/json"})
        urllib.request.urlopen(req, timeout=3).read()
        cls.http.shutdown(); cls.http.server_close(); cls.thread.join(timeout=2)

    def request(self, path, method="GET", body=None, token=None):
        headers = {"Content-Type":"application/json"}
        if token: headers["Authorization"] = "Bearer " + token
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=3) as r: return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e: return e.code, e.headers, e.read()

    def test_dify_endpoints_auth_and_console(self):
        for path in ("/dify/v1/info", "/dify/v1/parameters", "/dify/v1/meta", "/dify/v1/site"):
            status, _, raw = self.request(path, token="app-demo-dify-token")
            self.assertEqual(status, 200, raw)
        self.assertEqual(self.request("/dify/v1/info")[0], 401)
        status, _, raw = self.request("/dify/console/api/login", "POST", {"email":"admin","password":"admin"})
        self.assertEqual(status, 200); self.assertEqual(json.loads(raw)["data"]["access_token"], "console-admin-token")
        status, _, raw = self.request("/dify/console/api/apps", token="console-admin-token")
        self.assertEqual(status, 200); self.assertEqual(json.loads(raw)["total"], 1)

    def test_dify_blocking_and_sse(self):
        body={"query":"靶场测试","response_mode":"blocking","user":"test"}
        status, _, raw=self.request("/dify/v1/chat-messages","POST",body,"app-demo-dify-token")
        self.assertEqual(status,200); self.assertIn("靶场测试",json.loads(raw)["answer"])
        body["response_mode"]="streaming"
        status,headers,raw=self.request("/dify/v1/chat-messages","POST",body,"app-demo-dify-token")
        self.assertEqual(status,200); self.assertIn("text/event-stream",headers.get("Content-Type","")); self.assertIn(b"event: message_end",raw)

    def test_coze_legacy_and_prefixed(self):
        for path in ("/v1/chat/completions", "/coze/v1/chat/completions"):
            status,_,raw=self.request(path,"POST",{"messages":[{"role":"user","content":"hello"}]},"coze-demo-token")
            self.assertEqual(status,200,raw); self.assertIn("choices",json.loads(raw))

    def test_http_echo_and_local_health(self):
        self.assertEqual(self.request("/http/health")[0],200)
        status,_,raw=self.request("/http/example","POST",{"value":7},"http-demo-token")
        self.assertEqual(status,200); self.assertEqual(json.loads(raw)["received"]["value"],7)
        self.assertEqual(self.request("/http/example","POST",{})[0],401)

    def test_scenario_switch_and_reset(self):
        body={"platform":"dify","scenario":"unpublished","prompt":"seed test"}
        self.assertEqual(self.request("/control/config","PUT",body)[0],200)
        self.assertEqual(self.request("/dify/v1/info",token="app-demo-dify-token")[0],404)
        self.request("/control/reset","POST",{})
        self.assertEqual(self.request("/dify/v1/info",token="app-demo-dify-token")[0],200)

if __name__ == "__main__": unittest.main()
