"""Release-facing process, configuration and recovery contracts."""
from contextlib import closing
import dataclasses
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from sentinel.config import Config
from sentinel.diagnostics import readiness, backup_database
from sentinel.lifecycle import instance_lock
from sentinel.server import serve, LocalHTTPServer
from sentinel.store import Store


class OperationsTests(unittest.TestCase):
    def test_loopback_bind_does_not_use_reverse_dns(self):
        from http.server import BaseHTTPRequestHandler
        with patch('socket.getfqdn', side_effect=AssertionError('Unexpected DNS lookup')):
            server=LocalHTTPServer(('127.0.0.1',0),BaseHTTPRequestHandler)
            try:
                self.assertGreater(server.server_port,0)
                self.assertEqual(server.server_name,'localhost')
            finally:
                server.server_close()

    def test_process_lock_refuses_second_process_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            code = 'from sentinel.lifecycle import instance_lock\nimport sys\nwith instance_lock(sys.argv[1]): print("acquired")'
            with instance_lock(directory):
                child = subprocess.run([sys.executable, '-c', code, directory], capture_output=True, text=True)
                self.assertNotEqual(child.returncode, 0)
                self.assertIn('Another Mail Sentinel process', child.stderr)
            child = subprocess.run([sys.executable, '-c', code, directory], capture_output=True, text=True)
            self.assertEqual(child.returncode, 0, child.stderr)

    def test_bind_failure_does_not_start_application(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            with patch('sentinel.server.Application') as application:
                with self.assertRaises(OSError):
                    serve(Config(data_dir=directory), occupied.getsockname()[1])
                application.assert_not_called()
            self.assertFalse((Path(directory) / 'reports.sqlite3').exists())
            with instance_lock(directory):
                pass

    def test_numeric_config_does_not_accept_boolean_or_float(self):
        for name, value in [('queue_workers', True), ('max_steps', 3.5), ('model', 123), ('redaction_terms', [1])]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                dataclasses.replace(Config(), **{name:value}).validate()

    def test_backup_is_consistent_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            ident = store.save('message', {'status':'incomplete'})
            dest = Path(directory) / 'backup.sqlite3'
            backup_database(directory, dest)
            with closing(sqlite3.connect(dest)) as db:
                self.assertEqual(db.execute('SELECT id FROM reports').fetchone()[0], ident)
            before = dest.read_bytes()
            with self.assertRaises(FileExistsError):
                backup_database(directory, dest)
            self.assertEqual(dest.read_bytes(), before)
            self.assertIsNotNone(store.report(ident))

    def test_readiness_loads_real_catalog_without_querying_or_exposing_secrets(self):
        with patch.dict(os.environ, {'SENTINEL_API_KEY':'do-not-export-this'}):
            result = readiness(Config(provider='openai',model='configured',allow_external=True))
        self.assertNotIn('do-not-export-this', json.dumps(result))
        self.assertFalse(result['ready'])  # default required vendor adapter has no real evidence
        self.assertIn('reference_data', [x['check'] for x in result['checks']])
        result = readiness(Config(model='configured',check_modes={'verify_sender':'off'}))
        self.assertTrue(result['ready'])

    def test_cli_error_is_actionable_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'invalid.toml'
            config.write_text('max_steps = true\n')
            result = subprocess.run([sys.executable,'-m','sentinel','--config',str(config),'check'], capture_output=True,text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Invalid type for setting: max_steps',result.stderr)
            self.assertNotIn('Traceback',result.stderr)


    def test_monitor_survives_temporary_storage_error(self):
        from sentinel.queue import QueueService
        from unittest.mock import Mock
        store = Mock()
        store.paused.side_effect = [sqlite3.OperationalError("locked"), True]
        service = QueueService(Config(), store)
        waits = []
        def wait(_):
            waits.append(1)
            if len(waits) == 2:
                service.stop()
        with patch.object(service.stop_event, 'wait', side_effect=wait):
            service.run()
        self.assertEqual(store.paused.call_count, 2)
        self.assertEqual(service.last_error, 'local_persistence_error')
