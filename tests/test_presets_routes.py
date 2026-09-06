"""Local preset privacy and authenticated loading through the real HTTP service."""
import dataclasses
import json
import os
from pathlib import Path
import unittest
import urllib.error
import urllib.request
from sentinel.config import encode_toml
import test_ux_logic


class PresetHTTPTests(unittest.TestCase):
    setUp = test_ux_logic.HTTPUXTests.setUp
    stop = test_ux_logic.HTTPUXTests.stop
    api = test_ux_logic.HTTPUXTests.api

    def preset(self, **changes):
        root=Path(self.tmp.name)
        self.config.skills_dir=str(root/'skills')
        directory=root/'.local-presets';directory.mkdir(exist_ok=True)
        values=dataclasses.asdict(dataclasses.replace(self.config,**changes))
        (directory/'test-local.toml').write_text('\n'.join(k+' = '+encode_toml(v) for k,v in values.items()),'utf-8')
        return directory

    def rejected(self,path,data,code=400):
        with self.assertRaises(urllib.error.HTTPError) as error:self.api(path,data)
        self.assertEqual(error.exception.code,code)
        return error.exception.read().decode()

    def test_load_restores_settings_without_returning_or_saving_secret(self):
        root=self.preset(model='preset-model',imap_host='mail.example.test',imap_user='preset-user',timeout=90,imap_port=1993)
        (root/'password.secret').write_text('synthetic-secret-only')
        (root/'test-local.credentials.json').write_text(json.dumps({'imap_password_file':'password.secret'}))
        listing=self.api('presets')
        self.assertEqual(listing,{'presets':[{'id':'test-local','name':'test local'}]})
        result=self.api('presets/load',{'id':'test-local'})
        self.assertEqual(result,{'status':'saved'})
        self.assertEqual(self.config.model,'preset-model')
        self.assertEqual(self.config.imap_port,1993)
        self.assertEqual(self.config.timeout,90)
        self.assertEqual(os.environ[self.config.imap_password_env],'synthetic-secret-only')
        self.assertNotIn('synthetic-secret-only',json.dumps(self.api('settings')))
        self.assertNotIn('synthetic-secret-only',(Path(self.tmp.name)/'sentinel.toml').read_text())

    def test_missing_and_traversal_ids_cannot_load_arbitrary_files(self):
        self.preset()
        for ident in ['../sentinel','/tmp/private','test-local.toml','missing',5,None]:
            self.rejected('presets/load',{'id':ident})

    def test_preset_endpoints_require_authentication(self):
        self.preset()
        for route,data in [('presets',None),('presets/load',b'{"id":"test-local"}')]:
            req=urllib.request.Request(self.url+route,data=data)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req)
            self.assertEqual(error.exception.code,403)

    def test_busy_or_monitoring_keeps_current_configuration(self):
        self.preset(model='must-not-apply')
        self.application.busy=True
        self.rejected('presets/load',{'id':'test-local'})
        self.application.busy=False
        self.application.store.pause(False)
        self.rejected('presets/load',{'id':'test-local'})
        self.assertEqual(self.config.model,'test-model')

    def test_startup_fields_and_external_credential_paths_are_rejected(self):
        root=self.preset(data_dir=str(Path(self.tmp.name)/'other'))
        self.rejected('presets/load',{'id':'test-local'})
        root=self.preset(model='must-not-apply')
        (root.parent/'outside.secret').write_text('do-not-expose')
        (root/'test-local.credentials.json').write_text('{"imap_password_file":"../outside.secret"}')
        error=self.rejected('presets/load',{'id':'test-local'})
        self.assertNotIn('do-not-expose',error)
        self.assertEqual(self.config.model,'test-model')

    def test_symlinked_preset_cannot_escape_directory(self):
        root=self.preset()
        other=root.parent/'outside.toml';other.write_text('model="outside"')
        try:(root/'outside.toml').symlink_to(other)
        except (OSError,NotImplementedError):self.skipTest('Symlinks unavailable')
        self.assertEqual(len(self.api('presets')['presets']),1)
        self.rejected('presets/load',{'id':'outside'})

    def test_direct_view_urls_load_shell_without_exposing_local_settings(self):
        self.preset(imap_user='private-user-marker')
        base=self.url.removesuffix('api/')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for path in ['review','monitor','history','settings','history/report-1']:
            with opener.open(base+path) as response:
                self.assertEqual(response.status,200)
                self.assertIn('text/html',response.headers['Content-Type'])
                self.assertNotIn('private-user-marker',response.read().decode())
        for path in ['settings/unknown','.local-presets/test-local.toml']:
            with self.assertRaises(urllib.error.HTTPError):opener.open(base+path)
