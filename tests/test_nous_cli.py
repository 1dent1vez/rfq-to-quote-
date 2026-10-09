import asyncio
import json
import subprocess
from pathlib import Path


def test_semantic_scores_penalize_nulls_extras_without_evidence_confusion():
    from backend.nous_cli import score_fields
    expected = {'items': [{'reference': {'value': 'GP149', 'evidence': []}, 'quantity': {'value': 2, 'evidence': []}}]}
    actual = {'items': [{'reference': {'value': 'GP-149'}, 'quantity': {'value': 2}}]}
    score = score_fields(expected, actual)
    assert score['correct'] == 8 and score['total'] == 9
    assert score['mismatches'][0]['field'] == 'reference'
    assert score_fields(expected, {'items': [{}, {}]})['total'] == 18
    assert score_fields(expected, None)['correct'] == 0
    assert score_fields(expected, {'items': ['not an item object']})['correct'] == 0


def test_cli_only_allows_existing_synthetic_fixture_without_inference():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([str(root / '.venv/bin/python'), '-m', 'backend.nous_cli', 'extract', '--fixture', 'real-contact-history'], cwd=root, capture_output=True, text=True)
    assert result.returncode == 2
    assert 'invalid choice' in result.stderr


def test_evaluation_aggregates_real_pipeline_records_and_reads_back(tmp_path):
    from backend.nous_cli import evaluate, FIXTURES
    from backend.extraction import AttemptStore
    class MockProvider:
        version = 'mock-evaluation-test-only'
        def __init__(self):
            self.count = 0
        async def extract(self, message, schema):
            self.count += 1
            return next(c['expected'] for c in FIXTURES['cases'] if c['message'] == message)
        def audit_snapshot(self):
            return {'model_id': 'mock', 'call_id': self.count, 'usage': {'cost': 0}}
    provider = MockProvider()
    store = AttemptStore(tmp_path / 'attempts.db')
    artifact = asyncio.run(evaluate(provider, store))
    assert len(artifact['cases']) == 8
    assert artifact['summary']['contract_passes'] == 8
    assert artifact['summary']['catalog_status_passes'] == 8
    assert artifact['summary']['semantic_correct'] == artifact['summary']['semantic_total']
    assert artifact['summary']['inference_requests'] == 8
    for case in artifact['cases']:
        assert store.history(case['request_id'])[-1] == case['attempt']


def test_retry_preserves_initial_and_disallows_second_retry(tmp_path):
    from backend.nous_cli import evaluate, retry_evaluation, FIXTURES
    from backend.extraction import AttemptStore
    class MockProvider:
        version = 'mock-retry-test'
        def __init__(self):
            self.count = 0
        async def extract(self, message, schema):
            self.count += 1
            return next(c['expected'] for c in FIXTURES['cases'] if c['message'] == message)
        def audit_snapshot(self):
            return {'call_id': self.count, 'usage': {'cost': 0}}
    provider = MockProvider()
    store = AttemptStore(tmp_path / 'attempts.db')
    async def run():
        artifact = await evaluate(provider, store)
        original = json.loads(json.dumps(artifact['cases'][0]))
        retried = await retry_evaluation(provider, store, artifact, ['reference'])
        assert retried['cases'][0] == original
        assert len(retried['retries']) == 1
        assert retried['summary_after_retries']['inference_requests'] == 9
        import pytest
        with pytest.raises(ValueError, match='already retried'):
            await retry_evaluation(provider, store, retried, ['reference'])
        assert provider.count == 9
    asyncio.run(run())
