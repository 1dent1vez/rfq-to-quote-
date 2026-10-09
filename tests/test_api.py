import os
import sqlite3
import pytest
from fastapi.testclient import TestClient

# Keep the legacy module's import-time seed away from the existing database.
os.environ['RFQ_DB'] = os.path.join(os.environ['TMPDIR'], 'intake-tdd-import.sqlite3')
from backend.app import create_app

@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / 'test.db')), raise_server_exceptions=False)

def intake(client, text='pieza | referencia=DEMO-F100 | cantidad=2', request_id='r1'):
    return client.post('/api/cases', data={'request_id': request_id, 'customer': 'Cliente sintético', 'email_text': text})

def test_exact_reference_is_synthetic_intake_not_quote(client):
    response = intake(client)
    assert response.status_code == 201
    case = response.json()
    assert case['status'] == 'identified'
    assert case['extractor'] == 'deterministic-offline-v1'
    assert case['synthetic'] is True
    assert case['email_text'] == 'pieza | referencia=DEMO-F100 | cantidad=2'
    line = case['lines'][0]
    assert line['quantity'] == 2
    assert line['status'] == 'matched'
    assert line['compatibility'] == 'not_evaluated'
    assert line['evidence']['line'] == 1
    assert line['candidates'][0]['reference'] == 'DEMO-F100'
    assert line['candidates'][0]['synthetic'] is True
    assert not {'subtotal', 'tax', 'total', 'unit_price', 'cost'} & case.keys()
    catalog = client.get('/api/catalog').json()
    assert all(p['synthetic'] for p in catalog)
    assert not any('price' in p or 'stock' in p for p in catalog)


def test_repeated_reference_requires_manufacturer_not_auto_choice(client):
    text = 'pieza | referencia=DEMO-P200 | cantidad=4'
    case = intake(client, text).json()
    assert case['status'] == 'pending'
    line = case['lines'][0]
    assert line['status'] == 'pending'
    assert line['missing_fields'] == ['fabricante']
    assert len(line['candidates']) == 2
    assert line['clarifications']
    chosen = intake(client, text + ' | fabricante=Fábrica Beta Demo', 'r2').json()['lines'][0]
    assert chosen['status'] == 'matched'
    assert chosen['candidates'][0]['manufacturer'] == 'Fábrica Beta Demo'
    unknown = intake(client, 'pieza | referencia=NO-EXISTE | cantidad=1', 'r3').json()['lines'][0]
    assert unknown['status'] == 'pending'
    assert unknown['candidates'] == []
    assert unknown['missing_fields'] == ['referencia']
    wrong_maker = intake(client, text + ' | fabricante=No existe', 'r4').json()['lines'][0]
    assert wrong_maker['status'] == 'pending'
    assert wrong_maker['candidates'] == []
    assert wrong_maker['missing_fields'] == ['fabricante']


def test_vehicle_manufacturer_clarification_preserves_application_requirement(client):
    text = 'vehiculo | descripcion=pastillas delanteras | marca=Marca Demo | modelo=Uno | anio=2020 | motor=1.6 | cantidad=1 | fabricante=Fábrica Beta Demo'
    response = intake(client, text)
    assert response.status_code == 201
    line = response.json()['lines'][0]
    assert line['status'] == 'matched'
    assert line['compatibility'] == 'synthetic_application_only'
    assert line['candidates'][0]['manufacturer'] == 'Fábrica Beta Demo'
    partial = intake(client, text.replace(' | motor=1.6', ''), 'r2').json()['lines'][0]
    assert partial['status'] == 'pending'
    assert partial['missing_fields'] == ['motor']
    assert len(partial['candidates']) == 1
    unknown = intake(client, text.replace('Fábrica Beta Demo', 'Desconocido'), 'r3').json()['lines'][0]
    assert unknown['candidates'] == []
    assert unknown['status'] == 'pending'


def test_vehicle_matching_uses_only_complete_synthetic_applications_in_mixed_request(client):
    vehicle = 'vehiculo | descripcion=filtro de aceite | marca=Marca Demo | modelo=Uno | anio=2020 | motor=1.6 | cantidad=1'
    result = intake(client, 'pieza | referencia=DEMO-F100 | cantidad=2\n' + vehicle).json()
    assert result['status'] == 'identified'
    assert len(result['lines']) == 2
    line = result['lines'][1]
    assert line['status'] == 'matched'
    assert line['compatibility'] == 'synthetic_application_only'
    assert line['candidates'][0]['matching_applications'] == [{'make': 'Marca Demo', 'model': 'Uno', 'year': 2020, 'engine': '1.6', 'synthetic': True}]
    partial = intake(client, vehicle.replace(' | motor=1.6', ''), 'r2').json()['lines'][0]
    assert partial['status'] == 'pending'
    assert partial['missing_fields'] == ['motor']
    assert len(partial['candidates']) == 2
    assert partial['compatibility'] == 'not_evaluated'
    unknown = intake(client, vehicle.replace('anio=2020', 'anio=2030'), 'r3').json()['lines'][0]
    assert unknown['status'] == 'pending'
    assert unknown['candidates'] == []
    assert unknown['clarifications']
    ambiguous = intake(client, vehicle.replace('filtro de aceite', 'pastillas delanteras'), 'r4').json()['lines'][0]
    assert ambiguous['status'] == 'pending'
    assert len(ambiguous['candidates']) == 2
    assert ambiguous['missing_fields'] == ['referencia', 'fabricante']
    empty = intake(client, 'vehiculo | cantidad=1', 'r5').json()['lines'][0]
    assert empty['missing_fields'] == ['descripcion', 'marca', 'modelo', 'anio', 'motor']


@pytest.mark.parametrize('text,missing', [
    ('Please send a filter', 'formato'),
    ('pieza | referencia=DEMO-F100 | cantidad=-1', 'cantidad'),
    ('pieza | referencia=DEMO-F100 | cantidad=0', 'cantidad'),
    ('pieza | referencia=DEMO-F100 | cantidad=NaN', 'cantidad'),
    ('pieza | referencia=DEMO-F100 | cantidad=Infinity', 'cantidad'),
    ('pieza | referencia=DEMO-F100 | cantidad=2.5', 'cantidad'),
    ('pieza | referencia=DEMO-F100 | cantidad=1000001', 'cantidad'),
    ('pieza | referencia=DEMO-F100', 'cantidad'),
    ('pieza | cantidad=1', 'referencia'),
    ('pieza | referencia=DEMO-F100 | cantidad=1 | cantidad=2', 'formato'),
    ('pieza | referencia=DEMO-F100 | cantidad=1 | extra=x', 'formato'),
    ('pieza | referencia=DEMO-F100 | cantidad=1 | broken', 'formato'),
    ('foo | referencia=DEMO-F100 | cantidad=1', 'formato'),
    ('vehiculo | descripcion=filtro de aceite | marca=Marca Demo | modelo=Uno | anio=NaN | motor=1.6 | cantidad=1', 'anio'),
])
def test_invalid_line_is_pending_never_server_error(client, text, missing):
    response = intake(client, text)
    assert response.status_code == 201
    case = response.json()
    assert case['status'] == 'pending'
    line = case['lines'][0]
    assert line['status'] == 'pending'
    assert missing in line['missing_fields']
    assert line['compatibility'] == 'not_evaluated'
    assert line['clarifications']
    assert line['evidence']['text'] == text


@pytest.mark.parametrize('text', ['   ', '\n\n', 'x' * 20001, '\n'.join(['pieza'] * 101)], ids=['spaces', 'empty-lines', 'too-long', 'too-many-lines'])
def test_empty_or_oversized_request_is_rejected_without_write(client, text):
    assert intake(client, text).status_code == 422
    assert client.get('/api/cases').json() == []


def test_duplicate_id_fails_safely_and_persisted_detail_survives_restart(tmp_path):
    path = str(tmp_path / 'persistent.db')
    client = TestClient(create_app(path), raise_server_exceptions=False)
    case = intake(client).json()
    assert intake(client).status_code == 409
    assert intake(client, 'pieza | referencia=DEMO-F101 | cantidad=3').status_code == 409
    restarted = TestClient(create_app(path))
    assert restarted.get('/api/cases').json() == [case]
    assert restarted.get('/api/cases/' + case['id']).json() == case
    assert restarted.get('/api/cases/no-existe').status_code == 404
    assert restarted.post('/api/cases/' + case['id'] + '/approve').status_code == 404


@pytest.mark.parametrize('field,value', [('request_id', '   '), ('customer', ' '), ('request_id', 'x'*129), ('customer', 'x'*201)])
def test_invalid_envelope_is_rejected(client, field, value):
    data = {'request_id': 'r1', 'customer': 'Demo', 'email_text': 'pieza | referencia=DEMO-F100 | cantidad=1', field: value}
    assert client.post('/api/cases', data=data).status_code == 422
    assert client.get('/api/cases').json() == []


def test_production_frontend_is_served_locally_with_compiled_assets(client):
    import re
    page = client.get('/')
    assert page.status_code == 200
    assert 'Ingreso de refacciones' in page.text
    assert '<html lang="es">' in page.text
    asset = re.search(r'src="(/assets/[^\"]+\.js)"', page.text).group(1)
    assert client.get(asset).status_code == 200
    assert client.get('/api/no-existe').status_code == 404
