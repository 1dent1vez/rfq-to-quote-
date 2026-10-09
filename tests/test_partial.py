import json
import pytest


def test_partial_retains_independent_match(tmp_path):
    from backend.partial_cli import PartialStore, run_message
    message = 'hola; 2 GP-149; necesito balatas'
    store = PartialStore(tmp_path/'partial.sqlite3')
    row = run_message(message, store)
    assert row['status'] == 'partially_identified'
    assert row['lines'][0]['status'] == 'matched'
    assert row['lines'][0]['candidates']
    assert row['lines'][0]['compatibility'] == 'not_evaluated'
    assert row['commercial_ready'] is False and row['actionable'] is False
    assert row['original_message'] == message
    assert len(row['unresolved_fragments']) == 2
    for fragment in row['unresolved_fragments']:
        assert message[fragment['start']:fragment['end']] == fragment['text']
    assert store.history(row['request_id']) == [row]


@pytest.mark.parametrize('message,status,line_statuses', [
    ('2 GP-149; 3 ZZ-999', 'partially_identified', ['matched', 'pending']),
    ('2 GP-149; GAD-6554', 'partially_identified', ['matched', 'pending']),
    ('2 GP-149; GAD-6554 x3', 'identified', ['matched', 'matched']),
    ('necesito balatas', 'pending', []),
    ('2 GP-149 para Versa2021', 'partially_identified', ['matched']),
    ('2 GP-149 para Versa 2021', 'partially_identified', ['matched']),
    ('2 GP-149; 3 GP-149', 'identified', ['matched', 'matched']),
    ('2 GP-149 x3; 3 GAD-6554', 'partially_identified', ['pending', 'matched']),
    ('2 GP-149 o 3 GAD-6554', 'pending', ['pending', 'pending']),
    ('2 GP-149; 3 GAD-6554; solo originales', 'pending', ['pending', 'pending']),
    ('2 GP-149 sin sustitutos; 3 GAD-6554', 'partially_identified', ['pending', 'matched']),
    ('2 GP-149; 3 GP-149; total 5', 'pending', ['pending', 'pending']),
    ('2 GP-149 adicional; 3 GAD-6554', 'partially_identified', ['pending', 'matched']),
    ('hola; 2 GP-149; gracias', 'partially_identified', ['matched']),
])
def test_state_boundaries(tmp_path, message, status, line_statuses):
    from backend.partial_cli import PartialStore, run_message
    from backend.deterministic import parse_message
    row = run_message(message, PartialStore(tmp_path/'p.sqlite3'))
    assert row['status'] == status
    assert [line['status'] for line in row['lines']] == line_statuses
    original = parse_message(message)
    for key in ('result', 'rules', 'unresolved_fragments', 'quantity_gaps', 'year_candidates'):
        assert row[key] == original[key]
    assert all(line['compatibility'] == 'not_evaluated' for line in row['lines'])
    for flag in row['context_flags']:
        for evidence in flag['evidence']:
            assert message[evidence['start']:evidence['end']] == evidence['text']
    for line in row['lines']:
        if line['status'] == 'matched':
            assert line['candidates']
    if 'sin sustitutos' in message:
        assert row['lines'][0]['candidates'], 'Pending restriction preserves catalog evidence'


def test_cli_evaluation_and_snapshot_isolation(tmp_path, capsys):
    from backend.partial_cli import main, PartialStore
    from backend.deterministic_cli import BaselineStore
    old = tmp_path/'old.sqlite3'
    BaselineStore(old)
    before = old.read_bytes()
    with pytest.raises(ValueError):
        PartialStore(old)
    assert old.read_bytes() == before
    target = tmp_path/'evaluation.json'
    args = ['--store', str(tmp_path/'new.sqlite3')]
    assert main(args + ['evaluate', '--output', str(target)]) == 0
    capsys.readouterr()
    artifact = json.loads(target.read_text())
    assert artifact['original_artifacts_unchanged']
    broad = artifact['datasets']['existing_contract']['summary']
    curated = artifact['datasets']['baseline_numeric']['summary']
    assert (broad['evaluated_cases'], curated['evaluated_cases']) == (8, 17)
    assert (broad['populated_correct'], broad['populated_total']) == (3, 37)
    assert (curated['populated_correct'], curated['populated_total']) == (29, 29)
    assert artifact['detection_unchanged']
    before = target.read_bytes()
    with pytest.raises(ValueError):
        main(args + ['evaluate', '--output', str(target)])
    assert target.read_bytes() == before
    assert main(args + ['extract', '--message', '2 GP-149; GAD-6554 x3']) == 0
    row = json.loads(capsys.readouterr().out)
    assert row['status'] == 'identified'
    assert main(args + ['history', '--request-id', row['request_id']]) == 0
    assert json.loads(capsys.readouterr().out) == [row]


def test_strict_status_and_candidate_evidence(tmp_path):
    from backend.partial import request_status
    from backend.partial_cli import PartialStore, run_message
    from backend.app import CATALOG, identify
    from backend.extraction import validate_extraction, _identify_normalized
    from backend.normalization import normalize_extraction
    with pytest.raises(ValueError):
        request_status([{'status': 'identified'}], False)
    row = run_message('2 GP-149 sin sustitutos', PartialStore(tmp_path/'p.sqlite3'))
    original = _identify_normalized(normalize_extraction(validate_extraction(row['result'], row['original_message'])), CATALOG, identify)
    assert row['lines'][0]['candidates'] == original[0]['candidates']
    assert row['lines'][0]['evidence'] == original[0]['evidence']
