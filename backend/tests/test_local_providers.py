import hashlib
import hmac
import json

import httpx
import pytest

from backend.app.gateway import DiagnosticGateway
from backend.app.llm import GeminiLLMProvider, OllamaLLMProvider, create_llm_provider
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
async def test_gemini_uses_interactions_structured_output_without_leaking_key(system, monkeypatch):
    settings, *_ = system
    settings = settings.model_copy(update={
        'llm_provider': 'gemini',
        'gemini_api_key': settings.__class__(_env_file=None, gemini_api_key='unit-test-gemini-key').gemini_api_key,
    })
    requests = []
    real_client = httpx.AsyncClient

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url == 'https://generativelanguage.googleapis.com/v1beta/interactions'
        assert request.headers['x-goog-api-key'] == 'unit-test-gemini-key'
        assert 'unit-test-gemini-key' not in str(request.url)
        assert body['model'] == 'gemini-3.8-flash'
        assert body['store'] is False
        assert body['generation_config']['thinking_level'] == 'low'
        assert body['response_format']['mime_type'] == 'application/json'
        encoded_schema = json.dumps(body['response_format']['schema'])
        assert '"const"' not in encoded_schema
        assert '"maxLength"' not in encoded_schema
        assert '"$defs"' in encoded_schema
        assert '"enum": ["STOP"]' in encoded_schema
        assert body['input'] == '{"api_key":"[REDACTED]","observations":[]}'
        return httpx.Response(200, json={
            'status': 'completed',
            'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': '{"decision_type":"STOP","reason":"Insufficient evidence"}'}]}],
            'usage': {'total_input_tokens': 100, 'total_output_tokens': 12, 'total_thought_tokens': 8},
        })

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    provider = create_llm_provider(settings)
    assert isinstance(provider, GeminiLLMProvider)
    decision = await provider.decide_next_action({'api_key': 'must-not-leave-process', 'observations': []})
    assert decision.decision_type == 'STOP'
    assert len(requests) == 1
    assert provider.metrics['input_tokens'] == [100]
    assert provider.metrics['output_tokens'] == [12]
    assert provider.metrics['thought_tokens'] == [8]


@pytest.mark.asyncio
async def test_gemini_repairs_invalid_decision_once(system, monkeypatch):
    settings, *_ = system
    settings = settings.__class__(_env_file=None, gemini_api_key='unit-test-gemini-key')
    real_client = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        content = 'not JSON' if len(requests) == 1 else '{"decision_type":"STOP","reason":"Repaired"}'
        return httpx.Response(200, json={
            'status': 'completed',
            'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': content}]}],
        })

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    provider = GeminiLLMProvider(settings)
    assert (await provider.decide_next_action({'observations': []})).reason == 'Repaired'
    assert provider.metrics['invalid_json'] == 1
    assert provider.metrics['retries'] == 1
    assert 'previous response was invalid' in requests[1]['input']


@pytest.mark.asyncio
async def test_gemini_requires_key_and_official_https_endpoint(system):
    settings, *_ = system
    with pytest.raises(ValueError, match='GEMINI_API_KEY'):
        await GeminiLLMProvider(settings).decide_next_action({'observations': []})
    insecure = settings.__class__(_env_file=None, gemini_api_key='unit-test-gemini-key', gemini_base_url='http://example.com/v1beta')
    with pytest.raises(ValueError, match='generativelanguage.googleapis.com'):
        GeminiLLMProvider(insecure).endpoint()
    configured = settings.__class__(_env_file=None, gemini_api_key='unit-test-gemini-key', gemini_model='gemini/model')
    assert GeminiLLMProvider(configured).model_endpoint().endswith('/models/gemini%2Fmodel')


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
