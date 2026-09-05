"""Classify bounded provider errors without exposing echoed private inputs."""
import io
import json
import unittest
import urllib.error
from unittest.mock import patch, MagicMock
from sentinel.agent import Agent
from sentinel.config import Config
from sentinel.providers import Provider, ProviderError
from test_security import registry


class ContextErrorTests(unittest.TestCase):
    def test_lm_studio_error_is_actionable_without_echoing_body(self):
        body=b'{"error":"Engine error: Context size has been exceeded. PRIVATE EMAIL CONTENT"}'
        failure=urllib.error.HTTPError('http://127.0.0.1:1234/v1/chat/completions',400,'Bad Request',{},io.BytesIO(body))
        opener=MagicMock();opener.open.side_effect=failure
        with patch('urllib.request.build_opener',return_value=opener):
            with self.assertRaises(ProviderError) as caught:
                Provider(Config()).request('http://127.0.0.1:1234/v1/chat/completions',{}, {})
        self.assertEqual(caught.exception.code,'context_limit')
        self.assertNotIn('PRIVATE',str(caught.exception))

    def test_agent_preserves_safe_error_code_and_has_no_verdict(self):
        provider=MagicMock();provider.decide.side_effect=ProviderError('PRIVATE', 'context_limit')
        result=Agent(registry(language='cs'),provider).run()
        self.assertEqual(result['status'],'incomplete')
        self.assertIsNone(result['report'])
        self.assertEqual(result['events'][-1]['error_code'],'context_limit')
        self.assertIn('kontext',result['events'][-1]['message'])
        self.assertNotIn('PRIVATE',json.dumps(result))
