"""Opt-in offline partial intake v1; original baseline remains frozen."""
import argparse
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .partial import STATE_VERSION, context_flags, request_status
from .deterministic import parse_message, PARSER_VERSION
from .extraction import CONTRACT_VERSION, validate_extraction, _identify_normalized
from .normalization import normalize_extraction, NORMALIZATION_VERSION

ROOT = Path(__file__).resolve().parents[1]
STORE_PATH = ROOT/'data/partial-baseline-v1.sqlite3'


class PartialStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables - {'partial_intake_v1', 'sqlite_sequence'}:
                raise ValueError('Refusing non-partial database')
            db.execute('CREATE TABLE IF NOT EXISTS partial_intake_v1 (sequence INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE, data TEXT NOT NULL)')

    def append(self, record):
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO partial_intake_v1(request_id,data) VALUES (?,?)',
                       (record['request_id'], json.dumps(record, ensure_ascii=False, allow_nan=False)))

    def history(self, request_id):
        with sqlite3.connect(self.path) as db:
            return [json.loads(r[0]) for r in db.execute('SELECT data FROM partial_intake_v1 WHERE request_id=? ORDER BY sequence', (request_id,))]


def run_message(message, store):
    from .app import CATALOG, identify
    parsed = parse_message(message)
    record = {'audit_version': STATE_VERSION, 'state_version': STATE_VERSION,
              'request_id': 'partial-' + str(uuid.uuid4()), 'recorded_at': datetime.now(timezone.utc).isoformat(),
              'original_message': message, 'extractor_version': PARSER_VERSION,
              'contract_version': CONTRACT_VERSION, 'normalization_version': NORMALIZATION_VERSION,
              'inference_requests': 0, **parsed, 'normalization': None, 'lines': [],
              'commercial_ready': False, 'actionable': False}
    if parsed['result'] is not None:
        projection = normalize_extraction(validate_extraction(parsed['result'], message))
        record['normalization'] = projection.model_dump(mode='json')
        record['lines'] = _identify_normalized(projection, CATALOG, identify)
        for line in record['lines']:
            # Preserve the identifier's bounded status; request_status validates it.
            line.update(compatibility='not_evaluated', commercial_ready=False, actionable=False)
    record['context_flags'] = context_flags(message, parsed)
    for flag in record['context_flags']:
        if flag['blocks_line']:
            for index in flag['items']:
                line = record['lines'][index]
                line['status'] = 'pending'
                if 'unprocessed_context' not in line['missing_fields']:
                    line['missing_fields'].append('unprocessed_context')
                line['clarifications'].append('Contexto literal sin procesar; no autoriza completar esta línea.')
    record['status'] = request_status(record['lines'], bool(parsed['unresolved_fragments'] or parsed['quantity_gaps'] or parsed['uncertain_reference_candidates'] or parsed['year_candidates']))
    store.append(record)
    persisted = store.history(record['request_id'])[-1]
    if persisted != record:
        raise RuntimeError('Partial target readback mismatch')
    return persisted


def evaluate(store):
    import hashlib
    from collections import Counter
    from .deterministic_cli import populated_score, score_fields
    protected = json.loads((ROOT/'docs/partial-preservation-before.json').read_text())
    def unchanged():
        return all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == digest for path, digest in protected.items())
    if not unchanged():
        raise RuntimeError('Protected artifact changed before evaluation')
    previous = json.loads((ROOT/'docs/deterministic-baseline-evaluation.json').read_text())
    artifact = {'audit_version': STATE_VERSION, 'parser_version': PARSER_VERSION,
                'evaluated_at': datetime.now(timezone.utc).isoformat(), 'synthetic': True,
                'human_reviewed': False, 'inference_requests': 0,
                'confidence': 'Uncalibrated syntax only, no broad field accuracy improvement.',
                'comparison_source': 'docs/deterministic-baseline-evaluation.json (read-only original snapshots)',
                'original_artifacts_hashes': protected, 'datasets': {}, 'detection_unchanged': True}
    paths = {'existing_contract': ROOT/'tests/fixtures/extraction_es_v1.json',
             'baseline_numeric': ROOT/'tests/fixtures/deterministic_numeric_v1.json'}
    for name, path in paths.items():
        dataset = json.loads(path.read_text())
        old_rows = {row['id']: row for row in previous['datasets'][name]['cases']}
        rows = []
        for case in dataset['cases']:
            record = run_message(case['message'], store)
            old = old_rows[case['id']]['attempt']
            gold = validate_extraction(case['expected'], case['message']).model_dump(mode='json') if case['expected']['items'] else {'items': []}
            same = all(record[key] == old[key] for key in ('result', 'rules', 'unresolved_fragments', 'quantity_gaps', 'year_candidates', 'uncertain_reference_candidates'))
            artifact['detection_unchanged'] &= same
            rows.append({'id': case['id'], 'gold': gold, 'attempt': record, 'detection_unchanged': same,
                         'before_request_status': old['status'], 'before_line_statuses': [line['status'] for line in old['lines']],
                         'before_candidate_count': sum(len(line['candidates']) for line in old['lines']),
                         'after_candidate_count': sum(len(line['candidates']) for line in record['lines']),
                         'populated_gold_fields': populated_score(gold, record['result']),
                         'null_aware_fields': score_fields(gold, record['result'])})
        summary = {'evaluated_cases': len(rows), 'expected_cases': len(dataset['cases']),
                   'recognized_items': sum(len(row['attempt']['lines']) for row in rows),
                   'before_request_statuses': dict(Counter(row['before_request_status'] for row in rows)),
                   'after_request_statuses': dict(Counter(row['attempt']['status'] for row in rows)),
                   'before_line_statuses': dict(Counter(s for row in rows for s in row['before_line_statuses'])),
                   'after_line_statuses': dict(Counter(line['status'] for row in rows for line in row['attempt']['lines'])),
                   'before_candidate_count': sum(row['before_candidate_count'] for row in rows),
                   'after_candidate_count': sum(row['after_candidate_count'] for row in rows),
                   'inference_requests': 0}
        for key, prefix in [('populated_gold_fields', 'populated'), ('null_aware_fields', 'null_aware')]:
            correct = sum(row[key]['correct'] for row in rows)
            total = sum(row[key]['total'] for row in rows)
            summary.update({prefix+'_correct': correct, prefix+'_total': total})
        artifact['datasets'][name] = {'dataset_version': dataset['dataset_version'], 'fixture_path': str(path.relative_to(ROOT)), 'summary': summary, 'cases': rows}
    artifact['original_artifacts_unchanged'] = unchanged()
    if not artifact['original_artifacts_unchanged'] or not artifact['detection_unchanged']:
        raise RuntimeError('Partial evaluation preservation failed')
    return artifact


def main(argv=None):
    parser = argparse.ArgumentParser(description='Opt-in offline partial intake; no commercial authorization')
    parser.add_argument('--store', type=Path, default=STORE_PATH)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('extract').add_argument('--message', required=True)
    sub.add_parser('history').add_argument('--request-id', required=True)
    sub.add_parser('evaluate').add_argument('--output', type=Path, default=ROOT/'docs/partial-baseline-evaluation.json')
    args = parser.parse_args(argv)
    if args.command == 'evaluate':
        output_path = args.output.resolve()
        if output_path.exists() or output_path.suffix != '.json' or any(output_path.is_relative_to((ROOT/name).resolve()) for name in ('tests', 'backend', 'frontend', 'data')):
            raise ValueError('Evaluation requires a new unprotected JSON target')
    store = PartialStore(args.store)
    if args.command == 'extract':
        output = run_message(args.message, store)
    elif args.command == 'history':
        output = store.history(args.request_id)
    else:
        artifact = evaluate(store)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open('x') as stream:
            stream.write(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n')
        if json.loads(output_path.read_text()) != artifact:
            raise RuntimeError('Partial evaluation target readback mismatch')
        output = {'artifact': str(output_path), 'summaries': {name: data['summary'] for name, data in artifact['datasets'].items()},
                  'detection_unchanged': artifact['detection_unchanged'], 'original_artifacts_unchanged': artifact['original_artifacts_unchanged']}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
