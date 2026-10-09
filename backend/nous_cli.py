"""Explicit synthetic-only CLI; no UI/default provider change.

python -m backend.nous_cli evaluate
python -m backend.nous_cli extract --fixture reference
python -m backend.nous_cli history --request-id <printed id>
"""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid
from .extraction import AttemptStore, ExtractionOrchestrator, validate_extraction
from .nous_free import BASE_URL, MODEL_ID, NousFreeProvider, is_zero

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((ROOT / 'tests/fixtures/extraction_es_v1.json').read_text())
STORE_PATH = ROOT / 'data/nous-free-attempts.sqlite3'
BUDGET_PATH = ROOT / 'data/nous-free-budget.sqlite3'
FIELDS = ('reference', 'description', 'manufacturer', 'quantity', 'vehicle.make',
          'vehicle.model', 'vehicle.year', 'vehicle.engine', 'unsupported_concepts')


def field_value(item, name):
    if name == 'unsupported_concepts':
        return [f.get('value') for f in item.get(name, []) if isinstance(f, dict)]
    obj = item
    for key in name.split('.'):
        obj = (obj or {}).get(key) if isinstance(obj, dict) else None
    return obj.get('value') if isinstance(obj, dict) else None


def score_fields(expected, actual):
    """Source-order item alignment, null-aware semantic slots, not evidence score.

    Include extra items in denominator; missing items score zero even for null slots.
    Invalid evidence may still earn semantic scores but NEVER contract/catalog passes.
    """
    gold = expected['items']
    predicted = actual.get('items', []) if isinstance(actual, dict) else []
    if not isinstance(predicted, list):
        predicted = []
    total = max(len(gold), len(predicted)) * len(FIELDS)
    correct, mismatches = 0, []
    for index in range(max(len(gold), len(predicted))):
        for name in FIELDS:
            g = field_value(gold[index], name) if index < len(gold) else None
            p = field_value(predicted[index], name) if index < len(predicted) and isinstance(predicted[index], dict) else None
            equal = index < len(gold) and index < len(predicted) and isinstance(predicted[index], dict) and type(g) is type(p) and g == p
            correct += int(equal)
            if not equal:
                mismatches.append({'item': index, 'field': name, 'expected': g, 'actual': p})
    return {'correct': correct, 'total': total, 'accuracy': correct / total if total else 0, 'mismatches': mismatches}


async def run_fixture(provider, store, case):
    # Import only for an explicitly invoked command: app's existing default remains offline.
    from .app import CATALOG, identify
    request_id = 'nous-synthetic-' + case['id'] + '-' + str(uuid.uuid4())
    record = await ExtractionOrchestrator(provider, store, identify, timeout_seconds=75).run(request_id, case['message'], CATALOG)
    persisted = store.history(request_id)[-1]
    if persisted != record:
        raise RuntimeError('Persisted target differs from returned attempt')
    return persisted


async def evaluate(provider, store):
    artifact = {'evaluated_at': datetime.now(timezone.utc).isoformat(), 'endpoint': BASE_URL,
                'model_id': MODEL_ID, 'dataset_version': FIXTURES['dataset_version'],
                'synthetic': True, 'human_reviewed': False, 'real_provider_evaluated': not provider.version.startswith('mock'),
                'scoring': '9 null-aware semantic slots per source-order item; extra/missing items penalized; literal spans separately contract-validated',
                'retry_policy': 'No automatic retries; every failure retained', 'cases': []}
    for case in FIXTURES['cases']:
        record = await run_fixture(provider, store, case)
        actual = record['raw_output']
        scores = score_fields(case['expected'], actual)
        statuses = [line['status'] for line in record['lines']]
        exact = record['state'] == 'validated' and record['result'] == validate_extraction(case['expected'], case['message']).model_dump(mode='json')
        artifact['cases'].append({'id': case['id'], 'request_id': record['request_id'], 'attempt': record,
                                  'contract_pass': record['state'] == 'validated', 'exact_annotation_match': exact,
                                  'semantic_fields': scores, 'catalog_statuses': statuses,
                                  'expected_catalog_statuses': case['expected_catalog_status'],
                                  'catalog_status_pass': record['state'] == 'validated' and statuses == case['expected_catalog_status']})
        audit = record.get('provider_audit', {})
        if record['state'] in ('timeout', 'provider_error') or not is_zero((audit.get('usage') or {}).get('cost')):
            artifact['stopped_reason'] = 'Transport/provider error or unverified cost; remaining not sent'
            break
    cases = artifact['cases']
    artifact['not_run_case_ids'] = [c['id'] for c in FIXTURES['cases'] if c['id'] not in {r['id'] for r in cases}]
    total = sum(c['semantic_fields']['total'] for c in cases)
    correct = sum(c['semantic_fields']['correct'] for c in cases)
    artifact['summary'] = {'evaluated_cases': len(cases), 'expected_cases': len(FIXTURES['cases']),
                           'contract_passes': sum(c['contract_pass'] for c in cases),
                           'exact_annotation_matches': sum(c['exact_annotation_match'] for c in cases),
                           'catalog_status_passes': sum(c['catalog_status_pass'] for c in cases),
                           'semantic_correct': correct, 'semantic_total': total, 'semantic_accuracy': correct / total if total else 0,
                           'inference_requests': sum('call_id' in c['attempt'].get('provider_audit', {}) for c in cases),
                           'recorded_zero_cost_responses': sum(is_zero((c['attempt'].get('provider_audit', {}).get('usage') or {}).get('cost')) for c in cases)}
    return artifact


async def retry_evaluation(provider, store, artifact, case_ids):
    """Explicit single retries; preserve original evidence and budget ledger."""
    prior_ids = {c['id'] for c in artifact.get('retries', [])}
    if len(case_ids) != len(set(case_ids)) or prior_ids.intersection(case_ids):
        raise ValueError('Case already retried or duplicate selection')
    known = {c['id']: c for c in FIXTURES['cases']}
    original_ids = {c['id'] for c in artifact['cases']}
    if any(i not in original_ids or i not in known for i in case_ids):
        raise ValueError('Retry must reference an evaluated synthetic fixture')
    artifact.setdefault('retries', [])
    for case_id in case_ids:
        case = known[case_id]
        record = await run_fixture(provider, store, case)
        statuses = [line['status'] for line in record['lines']]
        artifact['retries'].append({'id': case_id, 'request_id': record['request_id'], 'attempt': record,
            'contract_pass': record['state'] == 'validated',
            'exact_annotation_match': record['state'] == 'validated' and record['result'] == validate_extraction(case['expected'], case['message']).model_dump(mode='json'),
            'semantic_fields': score_fields(case['expected'], record['raw_output']),
            'catalog_statuses': statuses, 'expected_catalog_statuses': case['expected_catalog_status'],
            'catalog_status_pass': record['state'] == 'validated' and statuses == case['expected_catalog_status']})
        if record['state'] in ('timeout', 'provider_error') or not is_zero((record.get('provider_audit', {}).get('usage') or {}).get('cost')):
            artifact['stopped_reason'] = 'Retry stopped: transport/provider failure or unknown cost'
            break
    latest = {c['id']: c for c in artifact['cases']}
    latest.update({c['id']: c for c in artifact['retries']})
    rows = list(latest.values())
    all_rows = artifact['cases'] + artifact['retries']
    correct = sum(c['semantic_fields']['correct'] for c in rows)
    total = sum(c['semantic_fields']['total'] for c in rows)
    artifact['summary_after_retries'] = {'evaluated_cases': len(rows), 'expected_cases': len(FIXTURES['cases']),
        'contract_passes': sum(c['contract_pass'] for c in rows),
        'exact_annotation_matches': sum(c['exact_annotation_match'] for c in rows),
        'catalog_status_passes': sum(c['catalog_status_pass'] for c in rows),
        'semantic_correct': correct, 'semantic_total': total, 'semantic_accuracy': correct / total if total else 0,
        'inference_requests': sum('call_id' in c['attempt'].get('provider_audit', {}) for c in all_rows),
        'recorded_zero_cost_responses': sum(is_zero((c['attempt'].get('provider_audit', {}).get('usage') or {}).get('cost')) for c in all_rows)}
    artifact['retry_policy'] = 'Explicit selected cases, at most one evaluation retry each, no automatic retries; initial failures preserved'
    return artifact


def ledger_summary():
    if not BUDGET_PATH.exists():
        return {'integration_requests_reserved': 0, 'prior_parent_smoke_requests': 1, 'authorized_total_max': 16}
    with sqlite3.connect(BUDGET_PATH) as db:
        count, verified = db.execute('SELECT COUNT(*), COALESCE(SUM(cost_verified), 0) FROM inference_calls').fetchone()
    return {'integration_requests_reserved': count, 'recorded_zero_cost_responses': verified,
            'prior_parent_smoke_requests': 1, 'combined_requests': count + 1, 'authorized_total_max': 16}


def main():
    parser = argparse.ArgumentParser(description='Synthetic fixtures ONLY, live Nous inference, opt-in')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('evaluate', help='Send eight existing synthetic fixtures, no automatic retries')
    retry = sub.add_parser('retry', help='Retry selected previously evaluated fixtures once, preserve initial failures')
    retry.add_argument('--fixture', required=True, action='append', choices=[c['id'] for c in FIXTURES['cases']])
    single = sub.add_parser('extract', help='One labeled synthetic message through production validation/audit')
    single.add_argument('--fixture', required=True, choices=[c['id'] for c in FIXTURES['cases']])
    history = sub.add_parser('history', help='Read persisted attempt; no inference')
    history.add_argument('--request-id', required=True)
    args = parser.parse_args()
    store = AttemptStore(STORE_PATH)
    if args.command == 'history':
        print(json.dumps(store.history(args.request_id), ensure_ascii=False, indent=2))
        return 0
    provider = NousFreeProvider(BUDGET_PATH)
    if args.command in ('evaluate', 'retry'):
        path = ROOT / 'docs/nous-free-evaluation.json'
        artifact = (asyncio.run(evaluate(provider, store)) if args.command == 'evaluate' else
                    asyncio.run(retry_evaluation(provider, store, json.loads(path.read_text()), args.fixture)))
        artifact['request_budget'] = ledger_summary()
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n')
        summary = artifact.get('summary_after_retries', artifact['summary'])
        print(json.dumps({'artifact': str(path), 'summary': summary, 'request_budget': artifact['request_budget']}, indent=2))
        return 0 if summary['contract_passes'] == len(FIXTURES['cases']) else 1
    case = next(c for c in FIXTURES['cases'] if c['id'] == args.fixture)
    record = asyncio.run(run_fixture(provider, store, case))
    print(json.dumps({'store': str(STORE_PATH), 'attempt': record, 'request_budget': ledger_summary()}, ensure_ascii=False, indent=2))
    return 0 if record['state'] == 'validated' else 1


if __name__ == '__main__':
    raise SystemExit(main())
