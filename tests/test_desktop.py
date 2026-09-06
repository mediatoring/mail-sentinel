import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from sentinel.config import load_config
from sentinel.desktop import open_app, session_url


class DesktopTests(unittest.TestCase):
    def test_start_background_reopen_and_reject_stale_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sentinel.toml';path.write_text('model = "test"\n')
            config=load_config(path)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            children=[];real_popen=subprocess.Popen
            def spawn(*args,**kwargs):
                child=real_popen(*args,**kwargs);children.append(child);return child
            try:
                with patch('sentinel.desktop.subprocess.Popen',side_effect=spawn),patch('sentinel.desktop.webbrowser.open',return_value=True) as browser:
                    open_app(config,path,port)
                    first=browser.call_args.args[0]
                    self.assertTrue(first.startswith(f'http://127.0.0.1:{port}/settings#token='))
                    open_app(config,path,port)
                    self.assertEqual(browser.call_count,2)
                    self.assertEqual(browser.call_args.args[0],first)
                    self.assertEqual(len(children),1)
                    metadata=Path(config.data_dir)/'browser-session.json'
                    if os.name!='nt':self.assertEqual(metadata.stat().st_mode & 0o777,0o600)
                    self.assertIsNone(session_url(config,Path(tmp)/'different.toml'))
                    saved=metadata.read_text();info=json.loads(saved);info['port']='8765';metadata.write_text(json.dumps(info))
                    self.assertIsNone(session_url(config,path));metadata.write_text(saved)
            finally:
                for child in children:
                    child.terminate()
                    try:child.wait(timeout=15)
                    except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
            self.assertIsNone(session_url(config,path))
