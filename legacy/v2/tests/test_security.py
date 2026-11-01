import atexit
import json, os, tempfile, threading, unittest, urllib.request, urllib.error, socket
# test_api sets these before server import; this file is also independently runnable.
_tmp = tempfile.TemporaryDirectory()
atexit.register(_tmp.cleanup)
os.environ.setdefault('AGENT_RANGE_STATE_PATH', os.path.join(_tmp.name, 'state.json'))
os.environ.setdefault('AGENT_RANGE_CONTROL_TOKEN', 'local-test-control')
os.environ.setdefault('AGENT_RANGE_DEMO_LOGIN', '1')
import server

class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.RangeHandler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.http.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join()
    def req(self,path,method='GET',body=None,token=None,raw=None):
        headers={'Content-Type':'application/json'}
        if token: headers['Authorization']='Bearer '+token
        payload=raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(urllib.request.Request(self.base+path,data=payload,headers=headers,method=method),timeout=3) as r: return r.status,json.loads(r.read())
        except urllib.error.HTTPError as e: return e.code,json.loads(e.read())
    def test_control_requires_secret(self):
        self.assertEqual(self.req('/control/state')[0],401)
        self.assertEqual(self.req('/control/reset','POST',{})[0],401)
        code,data=self.req('/control/state',token='local-test-control');self.assertEqual(code,200)
        self.assertTrue(all('value' not in t and 'token_hash' not in t for t in data['tokens']))
    def test_console_scope(self):
        for token in ('app-demo-dify-token','coze-demo-token','http-demo-token'):
            self.assertEqual(self.req('/dify/console/api/apps',token=token)[0],401)
        self.assertEqual(self.req('/dify/console/api/apps',token='console-admin-token')[0],200)
    def test_created_token_one_time_and_hashed(self):
        code,token=self.req('/control/tokens','POST',{'platform':'dify','name':'temporary'},'local-test-control')
        self.assertEqual(code,201); value=token['value'];self.assertEqual(self.req('/dify/v1/info',token=value)[0],200)
        with open(server.STATE_PATH,encoding='utf-8') as f: self.assertNotIn(value,f.read())
        code,state=self.req('/control/state',token='local-test-control')
        self.assertNotIn(value,json.dumps(state))
        self.assertEqual(self.req('/control/tokens/'+token['id'],'DELETE',token='local-test-control')[0],200)
        self.assertEqual(self.req('/dify/v1/info',token=value)[0],401)
    def test_unpublished_coze_all_paths(self):
        self.assertEqual(self.req('/control/config','PUT',{'platform':'coze','scenario':'unpublished','prompt':'test'},'local-test-control')[0],200)
        try:
            for path in ('/coze/v1/chat/completions','/coze/open_api/v2/chat','/v1/chat/completions','/open_api/v2/chat'):
                self.assertEqual(self.req(path,'POST',{'query':'hi'},'coze-demo-token')[0],404)
        finally: self.req('/control/reset','POST',{},'local-test-control')
    def test_invalid_json_and_large_body(self):
        self.assertEqual(self.req('/dify/v1/chat-messages','POST',token='app-demo-dify-token',raw=b'[]')[0],400)
        with socket.create_connection(('127.0.0.1', self.http.server_port), timeout=3) as sock:
            sock.sendall(b'POST /dify/v1/chat-messages HTTP/1.1\r\nHost: localhost\r\nContent-Length: 1000001\r\n\r\n')
            self.assertIn(b' 413 ', sock.recv(1024))
