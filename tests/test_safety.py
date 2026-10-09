"""Characterization/regression checks on the already-green intake slices."""
import json
import sqlite3
from fastapi.testclient import TestClient
from backend.app import create_app


def test_existing_industrial_rows_are_not_migrated_or_exposed(tmp_path):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE catalog(sku TEXT PRIMARY KEY, data TEXT, stock INTEGER); CREATE TABLE cases(id TEXT PRIMARY KEY, request_id TEXT, data TEXT);')
        db.execute('INSERT INTO catalog VALUES(?,?,?)', ('OLD', '{"price":"12"}', 7))
        db.execute('INSERT INTO cases VALUES(?,?,?)', ('old-case', 'old-id', '{"total":"24"}'))
    client = TestClient(create_app(str(path)))
    assert client.get('/api/cases').json() == []
    assert len(client.get('/api/catalog').json()) == 4
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM catalog').fetchall() == [('OLD', '{"price":"12"}', 7)]
        assert db.execute('SELECT * FROM cases').fetchall() == [('old-case', 'old-id', '{"total":"24"}')]


def test_blank_lines_keep_original_line_numbers_and_invalid_line_does_not_poison_valid_line(tmp_path):
    client = TestClient(create_app(str(tmp_path / 'mixed.db')))
    text = '\nnot supported\n\npieza | referencia=DEMO-F100 | cantidad=2\n'
    response = client.post('/api/cases', data={'request_id':'mixed', 'customer':'Demo', 'email_text':text})
    assert response.status_code == 201
    lines = response.json()['lines']
    assert [(line['evidence']['line'], line['status']) for line in lines] == [(2, 'pending'), (4, 'matched')]
    assert response.json()['email_text'] == text


def test_application_fields_are_correlated_to_the_same_catalog_row(tmp_path):
    path = tmp_path / 'applications.db'
    app = create_app(str(path))
    with sqlite3.connect(path) as db:
        product = json.loads(db.execute("SELECT data FROM seller_v2_catalog WHERE id='demo-filter-a'").fetchone()[0])
        product['applications'].append({'make':'Otra Marca Demo','model':'Dos','year':2021,'engine':'2.0','synthetic':True})
        db.execute('UPDATE seller_v2_catalog SET data=? WHERE id=?', (json.dumps(product), product['id']))
    client = TestClient(app)
    text = 'vehiculo | descripcion=filtro de aceite | marca=Marca Demo | modelo=Dos | anio=2021 | motor=2.0 | cantidad=1'
    case = client.post('/api/cases',data={'request_id':'correlated','customer':'Demo','email_text':text}).json()
    assert case['status'] == 'pending'
    assert case['lines'][0]['candidates'] == []


def test_reference_tokens_are_not_fuzzily_repaired(tmp_path):
    client = TestClient(create_app(str(tmp_path / 'exact.db')))
    response = client.post('/api/cases',data={'request_id':'exact','customer':'Demo','email_text':'pieza | referencia=demo-f100 | cantidad=1'})
    line = response.json()['lines'][0]
    assert line['fields']['referencia'] == 'demo-f100'
    assert line['status'] == 'pending'
    assert line['candidates'] == []
