"""Explicit local deterministic CLI. No model adapters, network, UI or daemon changes."""
import argparse
import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .deterministic import parse_message, PARSER_VERSION
from .extraction import CONTRACT_VERSION, validate_extraction, _identify_normalized
from .normalization import normalize_extraction, NORMALIZATION_VERSION

ROOT = Path(__file__).resolve().parents[1]
STORE_PATH = ROOT / 'data/deterministic-baseline-v1.sqlite3'
AUDIT_VERSION = 'deterministic-baseline-audit-v1'


class BaselineStore:
    """Append-only, versioned local snapshots; refuse foreign/previous databases."""
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables - {'deterministic_baseline_v1', 'sqlite_sequence'}:
                raise ValueError('Refusing non-baseline database')
            db.execute('CREATE TABLE IF NOT EXISTS deterministic_baseline_v1 (sequence INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE, data TEXT NOT NULL)')

    def append(self, record):
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO deterministic_baseline_v1(request_id,data) VALUES (?,?)',
                       (record['request_id'], json.dumps(record, ensure_ascii=False, allow_nan=False)))

    def history(self, request_id):
        with sqlite3.connect(self.path) as db:
            return [json.loads(r[0]) for r in db.execute('SELECT data FROM deterministic_baseline_v1 WHERE request_id=? ORDER BY sequence', (request_id,))]


def run_message(message, store):
    from .app import CATALOG, identify
    started = time.perf_counter()
    parsed = parse_message(message)
    record = {'audit_version': AUDIT_VERSION, 'request_id': 'baseline-' + str(uuid.uuid4()),
              'recorded_at': datetime.now(timezone.utc).isoformat(), 'original_message': message,
              'extractor_version': PARSER_VERSION, 'contract_version': CONTRACT_VERSION,
              'normalization_version': NORMALIZATION_VERSION, 'inference_requests': 0,
              **parsed, 'normalization': None, 'lines': [], 'status': 'pending'}
    if parsed['result'] is not None:
        result = validate_extraction(parsed['result'], message)
        projection = normalize_extraction(result)
        record['normalization'] = projection.model_dump(mode='json')
        record['lines'] = _identify_normalized(projection, CATALOG, identify)
        # Catalog lookup is not authority to discard unparsed constraints/context.
        blocking = parsed['unresolved_fragments'] or parsed['quantity_gaps'] or parsed['uncertain_reference_candidates']
        if blocking:
            for line in record['lines']:
                line.update(status='pending', candidates=[], compatibility='not_evaluated')
                line['missing_fields'].append('deterministic_handoff')
                line['clarifications'].append('Fragmentos sin resolver; revisión requerida, sin inferencias.')
        record['status'] = 'pending' if any(line['status'] == 'pending' for line in record['lines']) else 'identified'
    record['elapsed_seconds'] = time.perf_counter() - started
    store.append(record)
    persisted = store.history(record['request_id'])[-1]
    if persisted != record:
        raise RuntimeError('Baseline target readback mismatch')
    return persisted


# Frozen parity with nous_cli.score_fields and citation_cli.populated_score;
# copied here to keep the offline executable independent of provider imports.
FIELDS = ('reference', 'description', 'manufacturer', 'quantity', 'vehicle.make',
          'vehicle.model', 'vehicle.year', 'vehicle.engine', 'unsupported_concepts')


def field_value(item, name):
    if name == 'unsupported_concepts':
        return [f.get('value') for f in item.get(name, []) if isinstance(f, dict)]
    obj = item
    for key in name.split('.'):
        obj = (obj or {}).get(key) if isinstance(obj, dict) else None
    return obj.get('value') if isinstance(obj, dict) else None


def populated_score(expected, actual):
    gold = expected['items']
    predicted = actual.get('items', []) if isinstance(actual, dict) else []
    if not isinstance(predicted, list):
        predicted = []
    correct = total = 0
    for index, item in enumerate(gold):
        for name in FIELDS:
            g = field_value(item, name)
            if g is None or g == []:
                continue
            p = field_value(predicted[index], name) if index < len(predicted) and isinstance(predicted[index], dict) else None
            total += 1
            correct += int(type(g) is type(p) and g == p)
    return {'correct': correct, 'total': total, 'accuracy': correct / total if total else 0}


def score_fields(expected, actual):
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


def evaluate(store):
    artifact = {'audit_version': AUDIT_VERSION, 'parser_version': PARSER_VERSION,
                'evaluated_at': datetime.now(timezone.utc).isoformat(),
                'synthetic': True, 'human_reviewed': False, 'inference_requests': 0,
                'confidence': 'Uncalibrated syntactic evidence only; no statistical confidence or production benchmark.',
                'scoring': 'Unchanged source-order populated-gold and 9-slot null-aware type-exact semantics; extra/missing items penalized in null-aware score. Evidence/contract separately evaluated. Baseline-specific gold measures only the approved grammar, not broad extraction.',
                'datasets': {}}
    paths = {'existing_contract': ROOT/'tests/fixtures/extraction_es_v1.json',
             'baseline_numeric': ROOT/'tests/fixtures/deterministic_numeric_v1.json'}
    for name, path in paths.items():
        dataset = json.loads(path.read_text())
        rows = []
        for case in dataset['cases']:
            # No labels/catalog are arguments to the pure parser.
            record = run_message(case['message'], store)
            gold = validate_extraction(case['expected'], case['message']).model_dump(mode='json') if case['expected']['items'] else {'items': []}
            statuses = [line['status'] for line in record['lines']]
            rows.append({'id': case['id'], 'gold': gold, 'attempt': record,
                         'contract_pass': record['result'] is not None,
                         'exact_annotation_match': record['result'] is not None and record['result'] == gold,
                         'pending_envelope_pass': not gold['items'] and record['state'] == 'pending_no_explicit_items' and record['status'] == 'pending',
                         'populated_gold_fields': populated_score(gold, record['result']),
                         'null_aware_fields': score_fields(gold, record['result']),
                         'catalog_statuses': statuses, 'expected_catalog_statuses': case['expected_catalog_status'],
                         'catalog_status_pass': record['result'] is not None and statuses == case['expected_catalog_status']})
        summary = {'evaluated_cases': len(rows), 'expected_cases': len(dataset['cases']),
                   'recognized_items': sum(len(r['attempt']['result']['items']) if r['attempt']['result'] else 0 for r in rows),
                   'contract_passes': sum(r['contract_pass'] for r in rows),
                   'exact_annotation_matches': sum(r['exact_annotation_match'] for r in rows),
                   'pending_no_explicit_items': sum(r['attempt']['state'] == 'pending_no_explicit_items' for r in rows),
                   'pending_envelope_passes': sum(r['pending_envelope_pass'] for r in rows),
                   'catalog_status_passes': sum(r['catalog_status_pass'] for r in rows),
                   'identified_requests': sum(r['attempt']['status'] == 'identified' for r in rows),
                   'inference_requests': 0}
        for key, prefix in [('populated_gold_fields', 'populated'), ('null_aware_fields', 'null_aware')]:
            correct = sum(r[key]['correct'] for r in rows)
            total = sum(r[key]['total'] for r in rows)
            summary.update({prefix+'_correct': correct, prefix+'_total': total, prefix+'_accuracy': correct/total if total else 0})
        artifact['datasets'][name] = {'dataset_version': dataset['dataset_version'], 'fixture_path': str(path.relative_to(ROOT)), 'summary': summary, 'cases': rows}
    return artifact


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline deterministic baseline only; local messages, no inference')
    parser.add_argument('--store', type=Path, default=STORE_PATH)
    sub = parser.add_subparsers(dest='command', required=True)
    ev = sub.add_parser('evaluate')
    ev.add_argument('--output', type=Path, default=ROOT/'docs/deterministic-baseline-evaluation.json')
    ex = sub.add_parser('extract')
    source = ex.add_mutually_exclusive_group(required=True)
    source.add_argument('--fixture')
    source.add_argument('--message')
    history = sub.add_parser('history')
    history.add_argument('--request-id', required=True)
    args = parser.parse_args(argv)
    store = BaselineStore(args.store)
    if args.command == 'history':
        output = store.history(args.request_id)
    elif args.command == 'extract':
        if args.fixture:
            cases = json.loads((ROOT/'tests/fixtures/extraction_es_v1.json').read_text())['cases'] + json.loads((ROOT/'tests/fixtures/deterministic_numeric_v1.json').read_text())['cases']
            case = next((c for c in cases if c['id'] == args.fixture), None)
            if case is None:
                parser.error('Unknown synthetic fixture')
            message = case['message']
        else:
            message = args.message
        output = run_message(message, store)
    else:
        import hashlib
        protected = json.loads((ROOT/'docs/deterministic-preservation-before.json').read_text())
        output = evaluate(store)
        output['original_artifacts_hashes'] = protected
        output['original_artifacts_unchanged'] = all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == value for path, value in protected.items())
        if not output['original_artifacts_unchanged']:
            raise RuntimeError('Protected artifact hash changed')
        encoded = json.dumps(output, ensure_ascii=False, indent=2) + '\n'
        # Evaluation output cannot overwrite any labels, source code or previous records.
        protected_roots = [ROOT/'tests', ROOT/'backend', ROOT/'frontend', ROOT/'data']
        if (args.output.resolve() in {(ROOT/p).resolve() for p in protected}
                or any(args.output.resolve().is_relative_to(p.resolve()) for p in protected_roots)
                or args.output.suffix != '.json'):
            raise ValueError('Evaluation output must be an unprotected JSON artifact')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
        if json.loads(args.output.read_text()) != output:
            raise RuntimeError('Evaluation artifact readback mismatch')
        output = {'artifact': str(args.output), 'summaries': {k: v['summary'] for k, v in output['datasets'].items()}, 'original_artifacts_unchanged': True}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
