from fastapi.testclient import TestClient
from backend.app import create_app


def test_official_curated_reference_source_and_preserved_request(tmp_path):
    client = TestClient(create_app(tmp_path / 'v2.db'))
    catalog = client.get('/api/catalog').json()
    assert {p['reference'] for p in catalog} == {'GP-149','GA-306','GAC-2271','GAF-2271','GP-91','GAD-6554','GAC-2330','GAF-2330'}
    assert all(not p['synthetic'] and p['source']['printed_page'] == 69 and p['source']['edition'] == '2026' for p in catalog)
    text = 'pieza | referencia=GP-149 | cantidad=2'
    case = client.post('/api/cases', data={'request_id':'source','customer':'Taller Rivera (ficticio)','email_text':text}).json()
    assert case['status'] == 'identified'
    assert case['email_text'] == text
    assert case['lines'][0]['compatibility'] == 'not_evaluated'
    assert case['lines'][0]['candidates'][0]['source']['url'].startswith('https://gonher.com.mx/')
    assert client.get('/api/cases/'+case['id']).json() == case
    assert not any('price' in p or 'stock' in p for p in catalog)


def test_vehicle_normalization_alternatives_and_unknown_coverage(tmp_path):
    client = TestClient(create_app(tmp_path / 'vehicles.db'))
    def ask(text, id):
        return client.post('/api/cases',data={'request_id':id,'customer':'Los Pinos (ficticio)','email_text':text}).json()['lines'][0]
    base = ' VEHICULO | descripcion= FILTRO DE ACEITE | marca= nissan | modelo= versa | anio=2018 | motor=1.6 | cantidad=1'
    line = ask(base,'oil')
    assert line['status'] == 'matched'
    assert line['compatibility'] == 'source_catalog_claim_only'
    assert line['evidence']['text'] == base
    assert line['fields']['marca'] == 'nissan'
    assert line['candidates'][0]['reference'] == 'GP-149'
    assert ask(base.replace('2018','2021'),'new')['candidates'][0]['reference'] == 'GP-91'
    cabin = ask(base.replace('ACEITE','CABINA'),'cabin')
    assert cabin['missing_fields'] == ['seleccion']
    assert {p['reference'] for p in cabin['candidates']} == {'GAC-2271','GAF-2271'}
    assert 'alternativas' in ' '.join(cabin['clarifications'])
    selected = ask(base.replace('ACEITE','CABINA')+' | referencia= gaf-2271','selected')
    assert selected['status'] == 'matched'
    assert selected['candidates'][0]['reference'] == 'GAF-2271'
    assert ask(base.replace(' | anio=2018',''),'missing')['missing_fields'] == ['anio']
    unknown = ask(base.replace('2018','2030'),'unknown')
    assert unknown['status'] == 'pending' and not unknown['candidates']
    assert 'no demuestra incompatibilidad' in ' '.join(unknown['clarifications'])
    ref = ask('pieza | referencia= gp-149 | cantidad=2','ref')
    assert ref['status'] == 'matched' and ref['fields']['referencia'] == 'gp-149'
    assert not ask('pieza | referencia=GP149 | cantidad=2','bad')['candidates']


def test_seller_structured_mixed_lines_preserve_original_and_fields(tmp_path):
    client = TestClient(create_app(tmp_path / 'forms.db'))
    original = 'Dos GP-149 y un kit para Versa 2018, por favor.'
    fields = [{'mode':'pieza','referencia':' gp-149 ','cantidad':'2'}, {'mode':'vehiculo','descripcion':'filtro de cabina','marca':'Nissan','modelo':'Versa','anio':'2018','motor':'1.6','cantidad':'1'}]
    import json
    case = client.post('/api/cases', data={'request_id':'forms','customer':'Taller Rivera (ficticio)','email_text':original,'structured_lines':json.dumps(fields)}).json()
    assert case['structured_lines'] == fields
    assert case['email_text'] == original
    assert case['lines'][0]['status'] == 'matched'
    assert case['lines'][0]['evidence']['source'] == 'seller_form'
    assert case['lines'][1]['missing_fields'] == ['seleccion']
    assert client.get('/api/cases/'+case['id']).json() == case
    bad = client.post('/api/cases', data={'request_id':'bad','customer':'Ficticio','email_text':original,'structured_lines':'not json'})
    assert bad.status_code == 422


def test_structured_keys_cannot_inject_legacy_grammar(tmp_path):
    import json
    client = TestClient(create_app(tmp_path / 'injection.db'))
    response = client.post('/api/cases',data={'request_id':'injection','customer':'Ficticio','email_text':'Original','structured_lines':json.dumps([{'mode':'pieza','referencia':'GP-149','cantidad':'2','x | cantidad':'3'}])})
    assert response.status_code == 422
    assert client.get('/api/cases').json() == []


def test_explicit_old_database_keeps_catalog_and_history_isolated(tmp_path):
    import sqlite3
    path=tmp_path / 'old.db'
    with sqlite3.connect(path) as conn:
        conn.executescript('CREATE TABLE intake_catalog(id TEXT PRIMARY KEY, data TEXT); CREATE TABLE intake_cases(id TEXT PRIMARY KEY, request_id TEXT, data TEXT);')
        conn.execute('INSERT INTO intake_catalog VALUES(?,?)',('invented','{"reference":"DEMO"}'))
        conn.execute('INSERT INTO intake_cases VALUES(?,?,?)',('history','old','{"original":"preserve"}'))
    client=TestClient(create_app(path))
    assert len(client.get('/api/catalog').json()) == 8
    assert client.get('/api/cases').json() == []
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT * FROM intake_catalog').fetchall() == [('invented','{"reference":"DEMO"}')]
        assert conn.execute('SELECT * FROM intake_cases').fetchall() == [('history','old','{"original":"preserve"}')]
