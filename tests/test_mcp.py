import json
import os
import subprocess
import sys
import unittest
from sentinel.mcp import Session
from test_security import registry, finish


class MCPTests(unittest.TestCase):
    def test_stdio_handshake_and_evidence(self):
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'inspect_prompt_injection','arguments':{}}}]
        process=subprocess.run([sys.executable,'-m','sentinel','mcp','--demo','4'],input='\n'.join(json.dumps(r) for r in requests)+'\n',capture_output=True,text=True,encoding='utf-8',timeout=5,env={**os.environ,'PYTHONIOENCODING':'ascii'})
        self.assertEqual(process.returncode,0,process.stderr)
        outputs=[json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(outputs),2)
        self.assertEqual(outputs[0]['result']['protocolVersion'],'2025-06-18')
        obs=json.loads(outputs[1]['result']['content'][0]['text'])
        self.assertTrue(obs['observation']['indicator_found'])

    def test_completion_uses_same_guard(self):
        session=Session(registry());session.initialized=session.ready=True
        session.handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'verify_sender','arguments':{}}})
        response=session.handle({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'finish_investigation','arguments':finish(verdict='LOW_RISK')['arguments']}})
        report=json.loads(response['result']['content'][0]['text'])
        self.assertEqual(report['verdict'],'INCONCLUSIVE')
        self.assertFalse(report['checks_complete'])

    def test_arbitrary_file_and_write_tools_denied(self):
        s=Session(registry());s.initialized=s.ready=True
        for name,args in [('read_file',{'path':'/etc/passwd'}),('inspect_message',{'message_id':'other'}),('quarantine',{})]:
            response=s.handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}})
            self.assertTrue(response['result']['isError'])
