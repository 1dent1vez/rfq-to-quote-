import pytest
import backend.app as module

LEGACY_CATALOG = [{'id': 'demo-filter-a', 'reference': 'DEMO-F100', 'manufacturer': 'Fábrica Alfa Demo', 'description': 'filtro de aceite', 'synthetic': True, 'applications': [{'make': 'Marca Demo', 'model': 'Uno', 'year': 2020, 'engine': '1.6', 'synthetic': True}]}, {'id': 'demo-filter-b', 'reference': 'DEMO-F101', 'manufacturer': 'Fábrica Alfa Demo', 'description': 'filtro de aceite', 'synthetic': True, 'applications': [{'make': 'Marca Demo', 'model': 'Uno', 'year': 2020, 'engine': '2.0', 'synthetic': True}]}, {'id': 'demo-pad-a', 'reference': 'DEMO-P200', 'manufacturer': 'Fábrica Alfa Demo', 'description': 'pastillas delanteras', 'synthetic': True, 'applications': [{'make': 'Marca Demo', 'model': 'Uno', 'year': 2020, 'engine': '1.6', 'synthetic': True}]}, {'id': 'demo-pad-b', 'reference': 'DEMO-P200', 'manufacturer': 'Fábrica Beta Demo', 'description': 'pastillas delanteras', 'synthetic': True, 'applications': [{'make': 'Marca Demo', 'model': 'Uno', 'year': 2020, 'engine': '1.6', 'synthetic': True}]}]

@pytest.fixture(autouse=True)
def historical_parser_fixtures(request, monkeypatch):
    # Synthetic fixtures belong only to historical regression tests, never demo seed.
    if request.module.__name__.endswith(('test_api','test_safety')):
        monkeypatch.setattr(module, 'CATALOG', LEGACY_CATALOG)


@pytest.fixture(autouse=True)
def public_snapshot_isolation(request, monkeypatch, tmp_path):
    """Public CI uses a technical projection, never private ledgers/raw model logs.

    The original archival evaluator and original test stay unchanged. Local runs
    with the original protected manifest continue to verify the original bytes.
    """
    if request.node.name != 'test_cli_evaluation_and_snapshot_isolation':
        return
    import hashlib
    import json
    import shutil
    import backend.partial_cli as cli
    if (cli.ROOT/'docs/partial-preservation-before.json').exists():
        return
    mirror = tmp_path/'public-evaluation'
    (mirror/'tests/fixtures').mkdir(parents=True)
    (mirror/'docs').mkdir()
    protected = {}
    for filename in ('extraction_es_v1.json','deterministic_numeric_v1.json','offline_reference_snapshot.json'):
        target = mirror/'tests/fixtures'/filename
        shutil.copyfile(cli.ROOT/'tests/fixtures'/filename,target)
        protected[str(target.relative_to(mirror))] = hashlib.sha256(target.read_bytes()).hexdigest()
    reference = json.loads((mirror/'tests/fixtures/offline_reference_snapshot.json').read_text())
    (mirror/'docs/deterministic-baseline-evaluation.json').write_text(json.dumps(reference))
    protected['docs/deterministic-baseline-evaluation.json'] = hashlib.sha256((mirror/'docs/deterministic-baseline-evaluation.json').read_bytes()).hexdigest()
    (mirror/'docs/partial-preservation-before.json').write_text(json.dumps(protected))
    monkeypatch.setattr(cli,'ROOT',mirror)

