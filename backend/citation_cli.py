"""Opt-in one-shot, eight-fixture/two-free-model citation comparison, no retries."""
import argparse
import asyncio
import hashlib
import json
import sqlite3
import statistics
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from .citation import CitationResult, resolve_citations, RESOLUTION_VERSION
from .citation_free import CitationFreeProvider, MODELS, PROMPT_VERSION, PROMPT_SHA256, SYSTEM
from .extraction import AttemptStore, validate_extraction, CONTRACT_VERSION, _identify_normalized
from .normalization import normalize_extraction, NORMALIZATION_VERSION
from .nous_free import BASE_URL, SafetyStop, ResponseRejected, is_zero
from .nous_cli import FIXTURES, FIELDS, field_value, score_fields

ROOT = Path(__file__).resolve().parents[1]
BUDGET = ROOT / 'data/citation-free-budget.sqlite3'
ATTEMPTS = ROOT / 'data/citation-free-attempts.sqlite3'
ARTIFACT = ROOT / 'docs/citation-free-evaluation.json'


def populated_score(expected, actual):
    gold = expected['items']
    predicted = actual.get('items', []) if isinstance(actual, dict) else []
    if not isinstance(predicted, list): predicted = []
    correct = total = 0
    for index, item in enumerate(gold):
        for name in FIELDS:
            g = field_value(item, name)
            if g is None or g == []: continue
            p = field_value(predicted[index], name) if index < len(predicted) and isinstance(predicted[index], dict) else None
            total += 1
            correct += int(type(g) is type(p) and g == p)
    return {'correct': correct, 'total': total, 'accuracy': correct / total if total else 0}


async def run_fixture(provider, store, case):
    from .app import CATALOG, identify
    original = case['message']
    if not isinstance(original, str) or not original.strip() or len(original) > 20000 or len(original.splitlines()) > 100:
        raise ValueError('Original message outside existing input bounds')
    record = {'request_id': 'citation-synthetic-' + case['id'] + '-' + str(uuid.uuid4()),
              'attempt_id': str(uuid.uuid4()), 'original_message': original,
              'extractor_version': provider.version, 'contract_version': CONTRACT_VERSION,
              'resolution_version': RESOLUTION_VERSION, 'normalization_version': NORMALIZATION_VERSION,
              'state': 'started', 'status': 'pending', 'raw_output': None,
              'result': None, 'normalization': None, 'lines': []}
    store.append(record)
    started = time.monotonic()
    try:
        wire = await asyncio.wait_for(provider.extract(original, CitationResult.model_json_schema()), timeout=75)
    except ResponseRejected as exc:
        record.update(state='invalid_output', failure_type=type(exc).__name__, failure_reason=str(exc))
    except Exception as exc:
        record.update(state='provider_error', failure_type=type(exc).__name__)
    else:
        record['raw_output'] = wire
        try:
            result = resolve_citations(wire, original)
        except ValueError as exc:
            record.update(state='invalid_output', failure_type=type(exc).__name__, failure_reason=str(exc))
        else:
            projection = normalize_extraction(result)
            record.update(state='validated', result=result.model_dump(mode='json'),
                          normalization=projection.model_dump(mode='json'),
                          lines=_identify_normalized(projection, CATALOG, identify))
            record['status'] = 'pending' if any(line['status'] == 'pending' for line in record['lines']) else 'identified'
    record['elapsed_seconds'] = time.monotonic() - started
    record['provider_audit'] = provider.audit_snapshot()
    if record['raw_output'] is None:
        record['raw_output'] = record['provider_audit'].get('raw_wire')
    store.append(record)
    persisted = store.history(record['request_id'])[-1]
    if persisted != record: raise RuntimeError('Attempt readback mismatch')
    return persisted


def summarize(artifact):
    artifact['summaries'] = {}
    for model in MODELS:
        rows = [c for c in artifact['cases'] if c['model_id'] == model]
        latencies = [c['attempt']['provider_audit']['latency_seconds'] for c in rows if 'latency_seconds' in c['attempt']['provider_audit']]
        null_correct = sum(c['null_aware_fields']['correct'] for c in rows)
        null_total = sum(c['null_aware_fields']['total'] for c in rows)
        populated_correct = sum(c['populated_gold_fields']['correct'] for c in rows)
        populated_total = sum(c['populated_gold_fields']['total'] for c in rows)
        artifact['summaries'][model] = {'evaluated_cases': len(rows), 'expected_cases': 8,
            'inference_requests': sum('call_id' in c['attempt']['provider_audit'] for c in rows),
            'recorded_zero_cost_responses': sum(is_zero((c['attempt']['provider_audit'].get('usage') or {}).get('cost')) for c in rows),
            'contract_passes': sum(c['contract_pass'] for c in rows),
            'exact_annotation_matches': sum(c['exact_annotation_match'] for c in rows),
            'catalog_status_passes': sum(c['catalog_status_pass'] for c in rows),
            'populated_correct': populated_correct, 'populated_total': populated_total,
            'populated_accuracy': populated_correct / populated_total if populated_total else 0,
            'null_aware_correct': null_correct, 'null_aware_total': null_total,
            'null_aware_accuracy': null_correct / null_total if null_total else 0,
            'latency_seconds': {'count': len(latencies), 'mean': statistics.mean(latencies) if latencies else None,
                'median': statistics.median(latencies) if latencies else None, 'max': max(latencies) if latencies else None}}
    ran = {(c['model_id'], c['id']) for c in artifact['cases']}
    artifact['not_run'] = [{'model_id': m, 'id': c['id']} for m in MODELS for c in FIXTURES['cases'] if (m, c['id']) not in ran]


async def evaluate(providers, store, checkpoint=None):
    artifact = {'evaluated_at': datetime.now(timezone.utc).isoformat(), 'endpoint': BASE_URL,
                'synthetic': True, 'human_reviewed': False, 'dataset_version': FIXTURES['dataset_version'],
                'real_provider_evaluated': all(not p.version.startswith('mock') for p in providers),
                'prompt_version': PROMPT_VERSION, 'prompt_sha256': PROMPT_SHA256, 'frozen_system_prompt': SYSTEM,
                'resolution_version': RESOLUTION_VERSION, 'retry_policy': 'Exactly one attempt per fixture per model; no retries or prompt changes',
                'scoring': 'Primary: populated gold semantic slots (type exact), no evidence credit; extra/missing items penalized in secondary 9-slot null-aware score. Strict contract and full annotation/evidence equality separate. Source-order alignment.',
                'cases': []}
    for provider in providers:
        for case in FIXTURES['cases']:
            record = await run_fixture(provider, store, case)
            statuses = [line['status'] for line in record['lines']]
            gold = validate_extraction(case['expected'], case['message']).model_dump(mode='json')
            artifact['cases'].append({'model_id': provider.model, 'id': case['id'], 'request_id': record['request_id'], 'attempt': record,
                'contract_pass': record['state'] == 'validated',
                'exact_annotation_match': record['state'] == 'validated' and record['result'] == gold,
                'populated_gold_fields': populated_score(gold, record['raw_output']),
                'null_aware_fields': score_fields(gold, record['raw_output']),
                'catalog_statuses': statuses, 'expected_catalog_statuses': case['expected_catalog_status'],
                'catalog_status_pass': record['state'] == 'validated' and statuses == case['expected_catalog_status']})
            unknown_cost = not is_zero((record['provider_audit'].get('usage') or {}).get('cost'))
            stop = record['state'] == 'provider_error' or unknown_cost
            if stop:
                artifact['stopped_reason'] = 'Transport/safety failure or unverified cost; no remaining requests sent'
                if callable(getattr(provider, 'halt', None)): provider.halt(artifact['stopped_reason'])
            summarize(artifact)
            if checkpoint: checkpoint(artifact)
            if stop: return artifact
    summarize(artifact)
    return artifact


def main():
    parser = argparse.ArgumentParser(description='Approved synthetic-only citation comparison; no retry/extract/customer input')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('evaluate')
    history = sub.add_parser('history')
    history.add_argument('--request-id', required=True)
    args = parser.parse_args()
    store = AttemptStore(ATTEMPTS)
    if args.command == 'history':
        print(json.dumps(store.history(args.request_id), ensure_ascii=False, indent=2)); return 0
    if ARTIFACT.exists(): raise SafetyStop('Comparison artifact already exists; no rerun/cherry-picking')
    if BUDGET.exists():
        with sqlite3.connect(BUDGET) as db:
            if db.execute('SELECT COUNT(*) FROM inference_calls').fetchone()[0]: raise SafetyStop('Experiment already started; no rerun')
    old_paths = [ROOT/'data/nous-free-budget.sqlite3', ROOT/'data/nous-free-attempts.sqlite3', ROOT/'docs/nous-free-evaluation.json', ROOT/'tests/fixtures/extraction_es_v1.json']
    before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in old_paths}
    providers = [CitationFreeProvider(BUDGET, model=m) for m in MODELS]
    def checkpoint(artifact): ARTIFACT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n')
    artifact = asyncio.run(evaluate(providers, store, checkpoint))
    with sqlite3.connect(BUDGET) as db:
        rows = db.execute('SELECT audit, cost_verified FROM inference_calls').fetchall()
    artifact['request_budget'] = {'reserved': len(rows), 'limit': 16, 'per_model_limit': 8, 'verified_zero_cost': sum(row[1] for row in rows),
                                 'by_model': {m: sum(json.loads(row[0])['model_id'] == m for row in rows) for m in MODELS}}
    artifact['original_artifacts_hashes'] = before
    artifact['original_artifacts_unchanged'] = all(hashlib.sha256(p.read_bytes()).hexdigest() == before[str(p.relative_to(ROOT))] for p in old_paths)
    checkpoint(artifact)
    print(json.dumps({'summaries': artifact['summaries'], 'request_budget': artifact['request_budget'], 'not_run': artifact['not_run'], 'stopped_reason': artifact.get('stopped_reason')}, indent=2))
    return 0 if not artifact['not_run'] else 1


if __name__ == '__main__': raise SystemExit(main())
