"""Real local HTTP integration tests. No model inference or mailbox access."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cfg = Path(cls.tmp.name) / 'config.toml'
        cfg.write_text('data_dir = '+json.dumps(cls.tmp.name+'/data')+'\n')
        cls.process = subprocess.Popen([sys.executable,'-m','sentinel','--config',str(cfg),'serve','--port','0'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        line = cls.process.stdout.readline()
        match = re.search(r'(http://127.0.0.1:\d+)/#token=(\S+)',line)
        if not match:
            cls.process.terminate()
            raise RuntimeError('Server failed to start')
        cls.url,cls.token=match.groups()
    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.communicate(timeout=5)
        cls.tmp.cleanup()
    def request(self,path,data=None,authenticated=True,extra=None):
        headers={'Content-Type':'application/json'}
        if authenticated:headers['X-Sentinel-Token']=self.token
        headers.update(extra or {})
        req=urllib.request.Request(self.url+path,None if data is None else json.dumps(data).encode(),headers)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req,timeout=5) as r:return r.status,r.read(),r.headers
        except urllib.error.HTTPError as e:return e.code,e.read(),e.headers
    def test_rules_and_limits_save_as_valid_toml(self):
        original=json.loads(self.request('/api/settings')[1])
        changed={**original,'queue_workers':2,'check_modes':{**original['check_modes'],'verify_payment':'required'}}
        try:
            self.assertEqual(self.request('/api/settings',changed)[0],200)
            actual=json.loads(self.request('/api/settings')[1])
            self.assertEqual(actual['queue_workers'],2)
            self.assertEqual(actual['check_modes']['verify_payment'],'required')
            import tomllib
            content=tomllib.loads((Path(self.tmp.name)/'config.toml').read_text())
            self.assertEqual(content['check_modes']['verify_payment'],'required')
        finally:
            self.request('/api/settings',original)

    def test_queue_paging_is_bounded(self):
        code,body,_=self.request('/api/queue?page=0')
        self.assertEqual(code,200)
        self.assertLessEqual(len(json.loads(body)['items']),50)
        self.assertEqual(self.request('/api/queue?page=-1')[0],400)

    def test_unauthenticated_api_blocked(self):
        self.assertEqual(self.request('/api/state',authenticated=False)[0],403)
    def test_cross_origin_blocked_even_with_token(self):
        self.assertEqual(self.request('/api/connection',{},extra={'Origin':'https://evil.example'})[0],403)
    def test_dns_rebinding_host_rejected(self):
        self.assertEqual(self.request('/api/state',extra={'Host':'evil.example'})[0],403)
    def test_no_model_analysis_blocked(self):
        state=json.loads(self.request('/api/state')[1])
        self.assertEqual(self.request('/api/analyze',{'message_id':state['messages'][0]['id'],'consent':True})[0],400)
    def test_preview_protects_accounts(self):
        state=json.loads(self.request('/api/state')[1])
        code,body,_=self.request('/api/preview',{'message_id':state['messages'][0]['id']})
        self.assertEqual(code,200)
        self.assertNotIn(b'123456789/0800',body)
    def test_static_csp_and_no_session_token(self):
        code,body,headers=self.request('/',authenticated=False)
        self.assertEqual(code,200)
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
        self.assertNotIn(self.token.encode(),body)
    def test_arbitrary_file_route_rejected(self):
        self.assertEqual(self.request('/sentinel.toml')[0],404)
    def test_fake_approval_rejected(self):
        self.assertEqual(self.request('/api/approve',{'token':'fake','report_id':'fake'})[0],400)


if __name__=='__main__':unittest.main()
