"""HTTP transport mocks ONLY; real evaluation lives in backend.nous_cli."""
import asyncio
import json
import httpx
import pytest

from backend.extraction import ExtractionResult


def test_async_exact_free_model_transport(tmp_path):
    from backend.nous_free import NousFreeProvider, MODEL_ID
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': MODEL_ID, 'pricing': {'prompt': '0', 'completion': '0'}}]})
        return httpx.Response(200, json={'model': MODEL_ID, 'usage': {'cost': 0}, 'choices': [{'finish_reason': 'stop', 'message': {'content': '{"items":[{}]}'}}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = NousFreeProvider(tmp_path / 'budget.db', client=client)
            result = await provider.extract('Mensaje sintético', ExtractionResult.model_json_schema())
            assert result == {'items': [{}]}
            assert provider.audit_snapshot()['usage']['cost'] == 0
    asyncio.run(run())
    assert [r.method for r in calls] == ['GET', 'POST']
    assert all(str(r.url).startswith('http://127.0.0.1:8645/v1/') for r in calls)
    payload = json.loads(calls[1].content)
    assert payload['model'] == 'upstage/solar-mini4:free'
    assert payload['max_tokens'] == 4096
    assert payload['response_format'] == {'type': 'json_object'}
    assert '"additionalProperties": false' in payload['messages'][0]['content']
    assert calls[1].headers['authorization'] == 'Bearer local-proxy'


@pytest.mark.parametrize('models', [
    [], [{'id': 'upstage/solar-mini4', 'pricing': {'prompt': '0', 'completion': '0'}}],
    [{'id': 'upstage/solar-mini4:free'}],
    *[ [{'id': 'upstage/solar-mini4:free', 'pricing': pricing}] for pricing in (
        {'prompt': '0'}, {'prompt': '0.1', 'completion': '0'},
        {'prompt': '0', 'completion': None}, {'prompt': 'NaN', 'completion': '0'},
        {'prompt': False, 'completion': '0'}, {'prompt': '0', 'completion': '-1'},
    )],
])
def test_fresh_price_guard_prevents_any_inference(tmp_path, models):
    from backend.nous_free import NousFreeProvider, SafetyStop
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={'data': models})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = NousFreeProvider(tmp_path / 'budget.db', client=client)
            with pytest.raises(SafetyStop):
                await provider.extract('synthetic', ExtractionResult.model_json_schema())
    asyncio.run(run())
    assert calls == ['GET']


def test_expired_free_variant_is_never_called(tmp_path):
    from backend.nous_free import NousFreeProvider, SafetyStop, MODEL_ID
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={'data': [{'id': MODEL_ID, 'pricing': {'prompt': '0', 'completion': '0'}, 'expiration_date': '2000-01-01'}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(SafetyStop):
                await NousFreeProvider(tmp_path / 'budget.db', client=client).extract('synthetic', ExtractionResult.model_json_schema())
    asyncio.run(run())
    assert calls == ['GET']


@pytest.mark.parametrize('body', [
    {'usage': {'cost': 0}, 'choices': [{'finish_reason': 'stop', 'message': {'content': 'not JSON'}}]},
    {'usage': {'cost': 0}, 'choices': [{'finish_reason': 'length', 'message': {'content': '{"items":[{}]}'}}]},
    {'usage': {'cost': 0}, 'choices': [{'finish_reason': 'stop', 'message': {'refusal': 'no', 'content': '{"items":[{}]}'}}]},
])
def test_bad_response_is_rejected_and_retained(tmp_path, body):
    from backend.nous_free import NousFreeProvider, ResponseRejected, MODEL_ID
    def handler(request):
        return httpx.Response(200, json={'data': [{'id': MODEL_ID, 'pricing': {'prompt': '0', 'completion': '0'}}]} if request.method == 'GET' else body)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = NousFreeProvider(tmp_path / 'budget.db', client=client)
            with pytest.raises(ResponseRejected):
                await provider.extract('synthetic', ExtractionResult.model_json_schema())
            assert provider.audit_snapshot()['response'] == body
    asyncio.run(run())


@pytest.mark.parametrize('usage', [None, {}, {'cost': None}, {'cost': 0.001}, {'cost': False}])
def test_unknown_or_nonzero_cost_persistently_stops_remaining(tmp_path, usage):
    from backend.nous_free import NousFreeProvider, SafetyStop, MODEL_ID
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={'data': [{'id': MODEL_ID, 'pricing': {'prompt': '0', 'completion': '0'}}]} if request.method == 'GET' else {'usage': usage, 'choices': [{'finish_reason': 'stop', 'message': {'content': '{"items":[{}]}'}}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = NousFreeProvider(tmp_path / 'budget.db', client=client)
            with pytest.raises(SafetyStop):
                await provider.extract('synthetic', ExtractionResult.model_json_schema())
            fresh = NousFreeProvider(tmp_path / 'budget.db', client=client)
            with pytest.raises(SafetyStop):
                await fresh.extract('synthetic', ExtractionResult.model_json_schema())
    asyncio.run(run())
    assert calls == ['GET', 'POST']


def test_budget_caps_new_calls_at_fifteen_across_instances(tmp_path):
    from backend.nous_free import NousFreeProvider, SafetyStop, MODEL_ID
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={'data': [{'id': MODEL_ID, 'pricing': {'prompt': '0', 'completion': '0'}}]} if request.method == 'GET' else {'usage': {'cost': 0}, 'choices': [{'finish_reason': 'stop', 'message': {'content': '{"items":[{}]}'}}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            for _ in range(15):
                await NousFreeProvider(tmp_path / 'budget.db', client=client).extract('synthetic', ExtractionResult.model_json_schema())
            with pytest.raises(SafetyStop):
                await NousFreeProvider(tmp_path / 'budget.db', client=client).extract('synthetic', ExtractionResult.model_json_schema())
    asyncio.run(run())
    assert calls.count('POST') == 15


def test_timeout_stops_future_calls_with_unknown_cost(tmp_path):
    from backend.nous_free import NousFreeProvider, SafetyStop, MODEL_ID
    def handler(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': MODEL_ID, 'pricing': {'prompt': '0', 'completion': '0'}}]})
        raise httpx.ReadTimeout('mock timeout')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = NousFreeProvider(tmp_path / 'budget.db', client=client)
            with pytest.raises(TimeoutError):
                await provider.extract('synthetic', ExtractionResult.model_json_schema())
            with pytest.raises(SafetyStop):
                await provider.extract('synthetic', ExtractionResult.model_json_schema())
    asyncio.run(run())


def test_provider_audit_is_persisted_on_invalid_schema(tmp_path):
    from backend.nous_free import NousFreeProvider, MODEL_ID
    from backend.extraction import AttemptStore, ExtractionOrchestrator
    from backend.app import identify, CATALOG
    def handler(request):
        return httpx.Response(200, json={'data': [{'id': MODEL_ID, 'pricing': {'prompt': '0', 'completion': '0'}}]} if request.method == 'GET' else {'usage': {'cost': 0}, 'choices': [{'finish_reason': 'stop', 'message': {'content': '{"items":[{"stock":true}]}'}}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = NousFreeProvider(tmp_path / 'budget.db', client=client)
            store = AttemptStore(tmp_path / 'attempts.db')
            record = await ExtractionOrchestrator(provider, store, identify, timeout_seconds=75).run('synthetic-schema', 'Mensaje', CATALOG)
            assert record['state'] == 'invalid_output'
            assert record['provider_audit']['usage']['cost'] == 0
            assert store.history('synthetic-schema')[-1] == record
    asyncio.run(run())


def test_prompt_and_strict_schema_preserve_literal_unicode():
    from backend.nous_free import build_messages, strict_schema
    message = '😀 Dos GP149.\nGONHER'
    messages = build_messages(message)
    assert message == json.loads(messages[1]['content'])['original_message']
    assert json.loads(messages[1]['content'])['tokens'][1] == {'start': 2, 'end': 5, 'text': 'Dos'}
    assert 'manufacturer' in messages[0]['content']
    assert 'quantity' in messages[0]['content']
    assert 'Unicode' in messages[0]['content']
    schema = strict_schema(ExtractionResult.model_json_schema())
    assert schema['$defs']['RequestedItem']['required'] == list(schema['$defs']['RequestedItem']['properties'])
    assert schema['$defs']['RequestedItem']['additionalProperties'] is False
    assert '"$ref"' not in json.dumps(schema)
    assert '"evidence"' in messages[0]['content']
    assert 'description must be null' in messages[0]['content']


def test_concurrent_instances_same_ledger_never_overlap(tmp_path):
    from backend.nous_free import NousFreeProvider, MODEL_ID, SafetyStop
    active, peak = 0, 0
    async def handler(request):
        nonlocal active, peak
        if request.method == 'GET':
            await asyncio.sleep(0.01)
            return httpx.Response(200, json={'data': [{'id': MODEL_ID, 'pricing': {'prompt': '0', 'completion': '0'}}]})
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return httpx.Response(200, json={'usage': {'cost': 0}, 'choices': [{'finish_reason': 'stop', 'message': {'content': '{"items":[{}]}'}}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            a, b = [NousFreeProvider(tmp_path / 'budget.db', client=client) for _ in range(2)]
            outputs = await asyncio.gather(a.extract('synthetic', ExtractionResult.model_json_schema()), b.extract('synthetic', ExtractionResult.model_json_schema()), return_exceptions=True)
            assert all(isinstance(v, (dict, SafetyStop)) for v in outputs)
    asyncio.run(run())
    assert peak == 1
