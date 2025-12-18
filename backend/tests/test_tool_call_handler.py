import json
import types
import os
import pytest

# Ensure tests import the local module
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import tool_call_handler as tch

class DummyResp:
    def __init__(self, status=200, data=None, text=''):
        self.status_code = status
        self._data = data or {"status":"success"}
        self.text = text or json.dumps(self._data)
    def json(self):
        return self._data
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.setenv('OPENAI_ASSISTANT_ID', 'test-assistant')
    monkeypatch.setenv('AZURE_PROXY_URL', 'http://localhost:7071/api/proxy_router')
    yield

def test_make_response_tuple_when_no_azure_functions(monkeypatch):
    # Force AZURE_FUNCTIONS_AVAILABLE False
    monkeypatch.setattr(tch, 'AZURE_FUNCTIONS_AVAILABLE', False)
    body, status, headers = tch._make_response({"ok": True}, status_code=201)
    assert status == 201
    assert 'application/json' in headers.get('Content-Type')
    parsed = json.loads(body)
    assert parsed['ok'] is True

def test_execute_tool_call_get_success(monkeypatch):
    # Mock requests.get to return a DummyResp
    def fake_get(url, params=None, headers=None, timeout=None):
        return DummyResp(200, {"interactions": []})
    monkeypatch.setattr(tch.requests, 'get', fake_get)
    result_text, info = tch.execute_tool_call('get_interaction_history', {'limit': 5}, 'user1')
    parsed = json.loads(result_text)
    assert 'interactions' in parsed
    assert info['status'] == 'success'

def test_execute_tool_call_post_proxy_failure(monkeypatch):
    # Simulate missing proxy URL
    monkeypatch.setenv('AZURE_PROXY_URL', '')
    # Ensure POST path returns an error payload
    res_text, info = tch.execute_tool_call('some_tool', {'a': 1}, 'user1')
    parsed = json.loads(res_text)
    assert 'error' in parsed
    assert info['status'] == 'failed'
