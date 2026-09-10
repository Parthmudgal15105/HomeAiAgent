import hashlib
import hmac
import json

import httpx
import pytest

from backend.app.gateway import DiagnosticGateway
from backend.app.llm import OllamaLLMProvider
from backend.app.rag import LocalRAG
from conftest import REGISTRY


@pytest.mark.asyncio
async def test_ollama_repairs_invalid_json_once_and_preserves_local_contract(system, monkeypatch):
    settings, *_ = system
    requests = []
    real_client = httpx.AsyncClient
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.host == '127.0.0.1'
        assert body['stream'] is True
        assert isinstance(body['format'], dict)
        assert body['options']['temperature'] == 0
        content = 'not JSON' if len(requests) == 1 else '{"decision_type":"STOP","reason":"Insufficient evidence"}'
        return httpx.Response(200, content=json.dumps({'message': {'content': content}, 'done': True}).encode() + b'\n')
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    provider = OllamaLLMProvider(settings)
    decision = await provider.decide_next_action({'observations': []})
    assert decision.decision_type == 'STOP'
    assert provider.metrics['invalid_json'] == 1
    assert len(requests) == 2
    assert 'Repair' in requests[1]['messages'][-1]['content']


@pytest.mark.asyncio
async def test_rag_uses_local_vectors_threshold_and_idempotent_points(system, monkeypatch):
    settings, *_ = system
    requests = []
    real_client = httpx.AsyncClient
    class Embedding:
        async def embed(self, text):
            return [1.0, 0.0]
    def handler(request):
        body = json.loads(request.content) if request.content else {}
        requests.append((request.method, request.url.path, body))
        if request.method == 'GET':
            return httpx.Response(404, json={})
        if request.url.path.endswith('/points/query'):
            return httpx.Response(200, json={'result': {'points': [{'score': .8, 'payload': {'kind': 'runbook', 'text': 'Redis diagnostics'}}]}})
        return httpx.Response(200, json={'result': True})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    rag = LocalRAG(settings, Embedding())
    await rag.upsert('runbook:redis:0', 'Redis diagnostics password=never-store', 'runbook')
    await rag.upsert('runbook:redis:0', 'Redis diagnostics', 'runbook')
    results = await rag.retrieve('stuck jobs')
    upserts = [body for method, path, body in requests if path.endswith('/points')]
    assert upserts[0]['points'][0]['id'] == upserts[1]['points'][0]['id']
    assert 'never-store' not in json.dumps(upserts)
    assert requests[-1][2]['score_threshold'] == settings.rag_score_threshold
    assert requests[-1][2]['query'] == [1., 0.]
    assert results[0]['kind'] == 'runbook'


@pytest.mark.asyncio
async def test_gateway_write_signature_matches_gateway_protocol(system, monkeypatch):
    settings, *_ = system
    captured = []
    real_client = httpx.AsyncClient
    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={'tool': 'restart_container', 'ok': True, 'result': {}})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    gateway = DiagnosticGateway(settings)
    gateway._registry = REGISTRY
    args = {'container': 'sandbox'}
    await gateway.execute('restart_container', args, approval={'id': 'action-123', 'approval_status': 'APPROVED'})
    request = captured[0]
    expires = request.headers['X-Approval-Expires']
    canonical = json.dumps(args, sort_keys=True, separators=(',', ':'))
    signed = f'action-123:restart_container:{canonical}:{expires}'
    expected = hmac.new(settings.gateway_approval_secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    assert request.headers['X-Approval-Token'] == expected
    assert request.headers['X-Action-ID'] == 'action-123'
    assert request.headers['Authorization'] == 'Bearer ' + settings.gateway_token
