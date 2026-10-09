"""Provider-independent tests; all adapters below are MOCK, not AI inference."""
import importlib
import pytest
import asyncio
import json
from pathlib import Path


def test_contract_nested_forbid_span_bounds_and_no_identifier_repair():
    ex = extraction()
    for start, end in [(-1, 3), (5, 3), (0, 999), (True, 3)]:
        output = payload()
        output['items'][0]['reference']['evidence'][0].update(start=start, end=end)
        with pytest.raises(ValueError):
            ex.validate_extraction(output, 'Dos GP-149, por favor.')
    output = {'items': [{'vehicle': {'model': field('Versa', 'Versa'), 'fitment': True}}]}
    with pytest.raises(ValueError):
        ex.validate_extraction(output, 'Versa')
    message = 'dos GP149'
    result = ex.validate_extraction({'items': [{'reference': field(message, 'GP149'), 'quantity': field(message, 'dos', 2)}]}, message)
    from backend.app import identify, CATALOG
    assert ex.identify_validated(result, CATALOG, identify)[0]['candidates'] == []


def test_cancelled_mock_attempt_retains_started_snapshot(tmp_path):
    ex = extraction()
    from backend.app import identify, CATALOG

    class MockCancelledAdapter:
        version = 'mock-cancelled-v1'

        async def extract(self, original_message, schema):
            raise asyncio.CancelledError()

    store = ex.AttemptStore(tmp_path / 'cancelled.db')
    engine = ex.ExtractionOrchestrator(MockCancelledAdapter(), store, identify, timeout_seconds=1)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(engine.run('cancelled', 'Mensaje original', CATALOG))
    assert [entry['state'] for entry in store.history('cancelled')] == ['started']
    assert store.history('cancelled')[0]['status'] == 'pending'


@pytest.mark.parametrize('request_id', ['', ' ', 'x' * 129])
def test_request_identifier_limits_do_not_write_attempts(tmp_path, request_id):
    ex = extraction()
    store = ex.AttemptStore(tmp_path / 'ids.db')
    with pytest.raises(ValueError):
        asyncio.run(ex.ExtractionOrchestrator(MockAdapter(), store, lambda *_: [], timeout_seconds=1).run(request_id, 'Mensaje', []))
    assert store.history(request_id) == []


def test_invalid_correction_leaves_history_unchanged(tmp_path):
    ex = extraction()
    from backend.app import identify, CATALOG
    store = ex.AttemptStore(tmp_path / 'bad-revision.db')
    engine = ex.ExtractionOrchestrator(MockAdapter(), store, identify, timeout_seconds=1)
    initial = asyncio.run(engine.run('revise', 'Dos GP-149, por favor.', CATALOG))
    before = store.history('revise')
    with pytest.raises(ValueError):
        engine.correct('revise', initial['attempt_id'], payload(), actor='', reason='reason', catalog=CATALOG)
    with pytest.raises(ValueError):
        engine.correct('revise', initial['attempt_id'], {'items': [{'reference': field('invented', 'invented')}]}, actor='reviewer', reason='reason', catalog=CATALOG)
    assert store.history('revise') == before


def test_labeled_spanish_dataset_validates_without_inference():
    ex = extraction()
    from backend.app import identify, CATALOG
    path = Path(__file__).parent / 'fixtures' / 'extraction_es_v1.json'
    assert path.exists(), 'labeled evaluation dataset missing'
    dataset = json.loads(path.read_text())
    assert dataset['real_provider_evaluated'] is False
    assert dataset['kind'] == 'synthetic-agent-authored-contract-fixtures'
    assert dataset['human_reviewed'] is False
    assert len(dataset['cases']) == 8
    for case in dataset['cases']:
        result = ex.validate_extraction(case['expected'], case['message'])
        lines = ex.identify_validated(result, CATALOG, identify)
        assert [line['status'] for line in lines] == case['expected_catalog_status'], case['id']


def test_human_correction_appends_evidence_backed_revision_and_rejects_stale_parent(tmp_path):
    ex = extraction()
    from backend.app import identify, CATALOG
    store = ex.AttemptStore(tmp_path / 'corrections.db')
    engine = ex.ExtractionOrchestrator(MockAdapter(), store, identify, timeout_seconds=1)
    message = 'Dos GP-149, por favor.'
    initial = asyncio.run(engine.run('revise', message, CATALOG))
    corrected = engine.correct('revise', initial['attempt_id'], {'items': [{'reference': field(message, 'GP-149')}]},
                               actor='local-reviewer', reason='Cantidad requiere confirmar', catalog=CATALOG)
    assert corrected['state'] == 'corrected' and corrected['status'] == 'pending'
    assert corrected['parent_attempt_id'] == initial['attempt_id']
    assert corrected['original_message'] == message
    assert corrected['actor'] == 'local-reviewer'
    assert corrected['reason'] == 'Cantidad requiere confirmar'
    assert corrected['recorded_at'].endswith('+00:00')
    assert store.history('revise') == [store.history('revise')[0], initial, corrected]
    with pytest.raises(ValueError):
        engine.correct('revise', initial['attempt_id'], payload(message), actor='local-reviewer', reason='stale', catalog=CATALOG)
    assert len(store.history('revise')) == 3


@pytest.mark.parametrize('message', ['', ' ' * 3, 'x' * 20001, '\n'.join(['x'] * 101)])
def test_invalid_original_message_is_rejected_before_adapter(tmp_path, message):
    ex = extraction()
    store = ex.AttemptStore(tmp_path / 'envelope.db')
    engine = ex.ExtractionOrchestrator(MockAdapter(), store, lambda *_: pytest.fail('lookup must not run'), timeout_seconds=1)
    with pytest.raises(ValueError):
        asyncio.run(engine.run('invalid-envelope', message, []))
    assert store.history('invalid-envelope') == []


@pytest.mark.parametrize('timeout', [0, -1, float('inf'), float('nan')])
def test_timeout_configuration_must_be_positive_finite(tmp_path, timeout):
    ex = extraction()
    with pytest.raises(ValueError):
        ex.ExtractionOrchestrator(MockAdapter(), ex.AttemptStore(tmp_path / 'timeout.db'), lambda *_: [], timeout_seconds=timeout)


@pytest.mark.parametrize('raw', [object(), {'items': [], 'bad': float('nan')}, 'x' * 200001])
def test_unpersistable_mock_output_leaves_safe_invalid_attempt(tmp_path, raw):
    ex = extraction()
    from backend.app import identify, CATALOG

    class MockUnsafeAdapter:
        version = 'mock-unsafe-v1'

        async def extract(self, original_message, schema):
            return raw

    store = ex.AttemptStore(tmp_path / 'unsafe.db')
    attempt = asyncio.run(ex.ExtractionOrchestrator(MockUnsafeAdapter(), store, identify, timeout_seconds=1).run('unsafe', 'Mensaje', CATALOG))
    assert attempt['state'] == 'invalid_output'
    assert attempt['raw_output'] is None
    assert attempt['output_retention'] == 'omitted_unsafe_or_oversize'
    assert store.history('unsafe')[-1] == attempt


@pytest.mark.parametrize('behavior,state', [('timeout', 'timeout'), ('error', 'provider_error'), ('invalid', 'invalid_output')])
def test_failed_mock_attempts_persist_pending_without_exception_secrets(tmp_path, behavior, state):
    ex = extraction()
    from backend.app import identify, CATALOG

    class MockFailureAdapter:
        version = 'mock-failure-v1'

        async def extract(self, original_message, schema):
            if behavior == 'timeout':
                await asyncio.sleep(1)
            if behavior == 'error':
                raise RuntimeError('secret-token-must-not-be-stored')
            return {'items': [{'inventory': 100}]}

    store = ex.AttemptStore(tmp_path / 'failures.db')
    engine = ex.ExtractionOrchestrator(MockFailureAdapter(), store, identify, timeout_seconds=0.01)
    attempt = asyncio.run(engine.run('failed', '¿Tienes filtros?', CATALOG))
    assert attempt['state'] == state
    assert attempt['status'] == 'pending'
    assert attempt['result'] is None and attempt['lines'] == []
    assert store.history('failed')[-1] == attempt
    assert 'secret-token' not in str(store.history('failed'))
    if behavior == 'invalid':
        assert attempt['raw_output'] == {'items': [{'inventory': 100}]}


class MockAdapter:
    """TEST ONLY: returns labeled fixture, never real model inference."""
    version = 'mock-fixture-v1'

    async def extract(self, original_message, schema):
        assert schema['additionalProperties'] is False
        return payload(original_message)


def test_injected_mock_orchestration_persists_validated_attempt(tmp_path):
    ex = extraction()
    from backend.app import identify, CATALOG
    store = ex.AttemptStore(tmp_path / 'attempts.db')
    engine = ex.ExtractionOrchestrator(MockAdapter(), store, identify, timeout_seconds=1)
    message = 'Dos GP-149, por favor.'
    attempt = asyncio.run(engine.run('request-1', message, CATALOG))
    assert attempt['state'] == 'validated'
    assert attempt['status'] == 'identified'
    assert attempt['extractor_version'] == 'mock-fixture-v1'
    assert attempt['contract_version'] == ex.CONTRACT_VERSION
    assert attempt['original_message'] == message
    assert attempt['result']['items'][0]['quantity']['value'] == 2
    assert attempt['lines'][0]['candidates'][0]['reference'] == 'GP-149'
    reopened = ex.AttemptStore(tmp_path / 'attempts.db')
    assert reopened.history('request-1')[-1] == attempt
    assert reopened.history('request-1')[0]['state'] == 'started'
    with pytest.raises(ValueError):
        asyncio.run(engine.run('request-1', 'changed original', CATALOG))
    assert len(reopened.history('request-1')) == 2


@pytest.mark.parametrize('quantity', [True, '2', 2.0, 0, -1, 1000001, float('inf')])
def test_quantity_is_strict_positive_bounded_integer(quantity):
    output = payload()
    output['items'][0]['quantity']['value'] = quantity
    with pytest.raises(ValueError):
        extraction().validate_extraction(output, 'Dos GP-149, por favor.')


@pytest.mark.parametrize('name', ['candidates', 'fitment', 'prices', 'inventory'])
def test_model_cannot_supply_catalog_or_commercial_decisions(name):
    output = payload()
    output['items'][0][name] = []
    with pytest.raises(ValueError):
        extraction().validate_extraction(output, 'Dos GP-149, por favor.')


def test_unsupported_evidence_and_grammar_injection_rejected():
    ex = extraction()
    output = {'items': [{'unsupported_concepts': [field('kit', 'kit')]}]}
    with pytest.raises(ValueError):
        ex.validate_extraction(output, 'Dos GP-149')
    message = 'GP-149|cantidad=3'
    with pytest.raises(ValueError):
        ex.validate_extraction({'items': [{'reference': field(message, message)}]}, message)


def test_structured_conversion_uses_catalog_not_model_decisions():
    ex = extraction()
    from backend.app import identify, CATALOG
    message = 'Dos GP-149, por favor.'
    result = ex.validate_extraction(payload(message), message)
    lines = ex.identify_validated(result, CATALOG, identify)
    assert lines[0]['status'] == 'matched'
    assert lines[0]['candidates'][0]['reference'] == 'GP-149'
    assert lines[0]['compatibility'] == 'not_evaluated'
    assert lines[0]['evidence']['source'] == 'validated_extraction'
    unknown = ex.validate_extraction({'items': [{}]}, 'Necesito filtros')
    assert ex.identify_validated(unknown, CATALOG, identify)[0]['status'] == 'pending'
    unsupported = ex.validate_extraction({'items': [{'reference': field(message, 'GP-149'), 'quantity': field(message, 'Dos', 2), 'unsupported_concepts': [field(message, 'por favor.')]}]}, message)
    assert ex.identify_validated(unsupported, CATALOG, identify)[0]['status'] == 'pending'


def extraction():
    assert importlib.util.find_spec('backend.extraction') is not None, 'extraction foundation missing'
    return importlib.import_module('backend.extraction')


def span(message, text):
    start = message.index(text)
    return {'start': start, 'end': start + len(text), 'text': text}


def field(message, text, value=None):
    return {'value': text if value is None else value, 'evidence': [span(message, text)]}


def payload(message='Dos GP-149, por favor.'):
    return {'items': [{'reference': field(message, 'GP-149'), 'quantity': field(message, 'Dos', 2)}]}


def test_validated_contract_preserves_literal_evidence_and_unknowns():
    ex = extraction()
    message = 'Dos GP-149, por favor.'
    result = ex.validate_extraction(payload(message), message)
    assert result.items[0].quantity.value == 2
    assert result.items[0].description is None
    assert result.items[0].reference.evidence[0].text == 'GP-149'
    with pytest.raises(Exception):
        result.items[0].reference.value = 'GP149'


def test_rejects_forged_spans_and_ungrounded_literal_fields():
    ex = extraction()
    message = 'Dos GP-149, por favor.'
    for mutation in ('offset', 'text', 'value'):
        output = payload(message)
        ref = output['items'][0]['reference']
        if mutation == 'offset':
            ref['evidence'][0]['end'] += 1
        elif mutation == 'text':
            ref['evidence'][0]['text'] = 'GP149'
        else:
            ref['value'] = 'GP-91'
        with pytest.raises(ValueError):
            ex.validate_extraction(output, message)
