"""Local preset privacy and authenticated loading through the real HTTP service."""
import dataclasses
import json
import os
from pathlib import Path
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
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

    def test_partial_example_keeps_runtime_paths_and_unspecified_settings(self):
        root=self.preset()
        original=self.config.data_dir
        example=Path(__file__).resolve().parents[1]/'examples/local-preset.toml'
        (root/'example.toml').write_text(example.read_text('utf-8'),'utf-8')
        self.api('presets/load',{'id':'example'})
        self.assertEqual(self.config.data_dir,original)
        self.assertEqual(self.config.model,'openai/gpt-oss-20b')
        self.assertEqual(self.config.imap_host,'mail.example.com')
        (root/'invalid.toml').write_text('api_key = "must-not-accept"')
        self.rejected('presets/load',{'id':'invalid'})

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


class PresetSaveTests(unittest.TestCase):
    """Writing a preset is a credential boundary: names are constrained and the secret stays out of TOML and HTTP."""
    setUp = test_ux_logic.HTTPUXTests.setUp
    stop = test_ux_logic.HTTPUXTests.stop
    api = test_ux_logic.HTTPUXTests.api

    def directory(self):
        return Path(self.tmp.name)/'.local-presets'

    def rejected(self, path, data, code=400):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.api(path, data)
        self.assertEqual(error.exception.code, code)
        return error.exception.read().decode()

    def test_password_stays_out_of_toml_and_out_of_the_response(self):
        response = self.api('presets/save', {'name':'my-mailbox','imap_password':'synthetic-secret-only'})
        self.assertEqual(response['preset'], {'id':'my-mailbox','name':'my mailbox','password_stored':True})
        self.assertNotIn('synthetic-secret-only', json.dumps(response))
        root = self.directory()
        self.assertNotIn('synthetic-secret-only', (root/'my-mailbox.toml').read_text('utf-8'))
        self.assertEqual(json.loads((root/'my-mailbox.credentials.json').read_text('utf-8')), {'imap_password_file':'my-mailbox.secret'})
        self.assertEqual((root/'my-mailbox.secret').read_text('utf-8').strip(), 'synthetic-secret-only')
        for name in (() if os.name == 'nt' else ('my-mailbox.toml','my-mailbox.secret','my-mailbox.credentials.json')):
            self.assertEqual(oct((root/name).stat().st_mode & 0o777), '0o600', name)

    def test_saved_preset_restores_the_settings_it_captured(self):
        with patch.dict('os.environ', {'SENTINEL_IMAP_PASSWORD':''}):
            self.api('settings', {'model':'captured-model'})
            self.api('presets/save', {'name':'captured'})
            self.api('settings', {'model':'changed-model'})
            self.assertEqual(self.config.model, 'changed-model')
            self.api('presets/load', {'id':'captured'})
        self.assertEqual(self.config.model, 'captured-model')
        self.assertFalse((self.directory()/'captured.credentials.json').exists())

    def test_names_that_would_leave_the_preset_directory_are_refused(self):
        with patch.dict('os.environ', {'SENTINEL_IMAP_PASSWORD':''}):
            for name in ['../escape', 'sub/dir', '', '.hidden', 'a'*65, 'has space', '-leading']:
                with self.subTest(name=name):
                    self.rejected('presets/save', {'name':name})
        self.assertEqual(sorted(p.name for p in self.directory().glob('*')) if self.directory().exists() else [], [])

    def test_existing_preset_is_not_overwritten_unless_asked(self):
        with patch.dict('os.environ', {'SENTINEL_IMAP_PASSWORD':''}):
            self.api('presets/save', {'name':'twice'})
            self.rejected('presets/save', {'name':'twice'})
            self.assertEqual(self.api('presets/save', {'name':'twice','overwrite':True})['preset']['id'], 'twice')

    def test_unknown_or_mistyped_preset_fields_are_refused(self):
        with patch.dict('os.environ', {'SENTINEL_IMAP_PASSWORD':''}):
            self.rejected('presets/save', {'name':'x','data_dir':'/tmp'})
            self.rejected('presets/save', {'name':'x','overwrite':'yes'})
            self.rejected('presets/save', {'name':123})


class FolderBrowsingTests(unittest.TestCase):
    """A folder chosen in the review view reaches an IMAP SELECT, so it passes configuration validation first."""
    setUp = test_ux_logic.HTTPUXTests.setUp
    stop = test_ux_logic.HTTPUXTests.stop
    api = test_ux_logic.HTTPUXTests.api

    def rejected(self, data, code=400):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.api('imap', data)
        self.assertEqual(error.exception.code, code)

    def test_folder_names_that_could_break_out_of_the_command_are_refused(self):
        with patch('sentinel.server.Mailbox') as mailbox:
            for folder in ['', 'has"quote', 'back\\slash', 'line\nbreak', 'null\x00byte']:
                with self.subTest(folder=folder):
                    self.rejected({'folder': folder})
            self.rejected({'folder': 993})
            mailbox.assert_not_called()

    def test_a_chosen_folder_is_used_without_changing_saved_settings(self):
        with patch('sentinel.server.Mailbox') as mailbox:
            mailbox.return_value.fetch.return_value = []
            result = self.api('imap', {'folder': 'INBOX.Archive'})
        self.assertEqual(result, {'count': 0, 'folder': 'INBOX.Archive'})
        self.assertEqual(mailbox.call_args.args[0].imap_folder, 'INBOX.Archive')
        self.assertEqual(self.config.imap_folder, 'AI-review')

    def test_omitted_folder_keeps_the_configured_one(self):
        with patch('sentinel.server.Mailbox') as mailbox:
            mailbox.return_value.fetch.return_value = []
            self.assertEqual(self.api('imap', {})['folder'], 'AI-review')
        self.assertEqual(mailbox.call_args.args[0].imap_folder, 'AI-review')
