"""Real JSON transport regressions for Unicode scalar validation, without inference."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.portfolio import create_app


@pytest.fixture
def unicode_client(tmp_path):
    path = tmp_path / 'unicode.sqlite3'
    with TestClient(create_app(path), raise_server_exceptions=False) as client:
        yield client, path


def raw_post(client, url, payload):
    # HTTPX json= encodes strict UTF-8 before reaching the app. Raw ASCII JSON
    # exercises the actual escaped-surrogate input received by FastAPI instead.
    body = json.dumps(payload, ensure_ascii=True).encode('ascii')
    return client.post(url, content=body, headers={'Content-Type': 'application/json'})


def persisted_state(path):
    with sqlite3.connect(path) as conn:
        return '\n'.join(conn.iterdump())


def intake_payload():
    return {'request_id': 'unicode-test', 'customer': 'Taller ficticio',
            'message': '2 GP-149; entrega urgente', 'suggestions': True}


def review_payload(case):
    return {'version': case['version'], 'actor': 'Vendedor demo',
            'reason': 'Cliente confirma alcance y entrega local',
            'supplement': 'Confirmado: dos GP-149 por referencia y entrega local.',
            'lines': [{'id': '0', 'product_id': 'gonher-gp-149', 'quantity': 2,
                       'scope': 'reference', 'vehicle': None}],
            'fragments': [{'id': f['id'], 'kind': 'resolved_context',
                           'reason': 'Entrega local acordada', 'line_id': None}
                          for f in case['fragments']]}


def mutation_payload(case):
    return {'version': case['version'], 'actor': 'Vendedor demo',
            'reason': 'Confirmo revisión comercial explícita'}


CASES = (
    [('intake', (field,)) for field in ('request_id', 'customer', 'message')]
    + [('intake', ('manual_lines', 0, 'reference'))]
    + [('review', (field,)) for field in ('actor', 'reason', 'supplement')]
    + [('review', ('lines', 0, field)) for field in ('id', 'product_id', 'scope')]
    + [('review', ('lines', 0, 'vehicle', field)) for field in ('make', 'model', 'engine')]
    + [('review', ('fragments', 0, field)) for field in ('id', 'kind', 'reason', 'line_id')]
    + [('draft', (field,)) for field in ('actor', 'reason')]
    + [('approve', (field,)) for field in ('actor', 'reason', 'snapshot')]
    + [('inventory', (field,)) for field in ('actor', 'reason', 'price', 'cost')]
    + [('reset', (field,)) for field in ('actor', 'reason', 'confirmation')]
)


@pytest.mark.parametrize('surrogate', ['\ud800', '\udfff'], ids=['high', 'low'])
@pytest.mark.parametrize('operation,field_path', CASES,
                         ids=[op + '-' + '-'.join(map(str, path)) for op, path in CASES])
def test_escaped_unpaired_surrogate_returns_422_without_persistence(unicode_client, operation, field_path, surrogate):
    client, path = unicode_client
    case = raw_post(client, '/api/requests', intake_payload()).json()
    if operation in ('draft', 'approve'):
        case = raw_post(client, f"/api/requests/{case['id']}/review", review_payload(case)).json()
    if operation == 'approve':
        case = raw_post(client, f"/api/requests/{case['id']}/draft", mutation_payload(case)).json()
    url = f"/api/requests/{case['id']}/{operation}"
    if operation == 'intake':
        url, payload = '/api/requests', {**intake_payload(), 'request_id': 'new-unicode-test'}
        if field_path[0] == 'manual_lines':
            payload.update(suggestions=False, manual_lines=[{'reference': 'GP-149', 'quantity': 2}])
    elif operation == 'review':
        payload = review_payload(case)
        if 'vehicle' in field_path:
            payload['lines'][0].update(scope='vehicle', vehicle={'make': 'Nissan', 'model': 'Versa', 'year': 2018, 'engine': '1.6'})
    elif operation in ('draft', 'approve'):
        payload = mutation_payload(case)
        if operation == 'approve':
            payload['snapshot'] = case['quote']['snapshot']
    elif operation == 'inventory':
        url = '/api/demo/inventory/gonher-gp-149'
        payload = {**mutation_payload({'version': 1}), 'price': '150.00', 'cost': '90.00', 'on_hand': 20}
    else:
        url = '/api/demo/reset'
        payload = {'confirmation': 'RESET PORTFOLIO DEMO', 'actor': 'Operador demo', 'reason': 'Restablecer demostración ficticia'}
    target = payload
    for key in field_path[:-1]:
        target = target[key]
    # Prefix preserves length/substance constraints where applicable.
    target[field_path[-1]] = 'Contenido válido ' + surrogate
    before = persisted_state(path)
    response = raw_post(client, url, payload)
    after = persisted_state(path)
    assert after == before, 'Rejected Unicode must not change any persisted table'
    assert response.status_code == 422, response.text
    assert response.json()['detail']


@pytest.mark.parametrize('label', ['Español: revisión, acción, niño', 'Unicode: 😀 🚗'])
def test_valid_unicode_is_preserved_through_quote_and_inventory(unicode_client, label):
    client, path = unicode_client
    payload = {**intake_payload(), 'request_id': label, 'customer': label,
               'message': '2 GP-149; ' + label}
    response = raw_post(client, '/api/requests', payload)
    assert response.status_code == 201, response.text
    case = response.json()
    assert case['original']['message'] == payload['message']
    assert case['request_id'] == label and case['customer'] == label
    review = review_payload(case)
    review.update(actor=label, reason=label, supplement=label)
    for fragment in review['fragments']:
        fragment['reason'] = label
    response = raw_post(client, f"/api/requests/{case['id']}/review", review)
    assert response.status_code == 200, response.text
    case = response.json()
    assert case['supplements'][0]['text'] == label
    response = raw_post(client, f"/api/requests/{case['id']}/draft",
                        {**mutation_payload(case), 'actor': label, 'reason': label})
    assert response.status_code == 200, response.text
    case = response.json()
    response = raw_post(client, f"/api/requests/{case['id']}/approve",
                        {**mutation_payload(case), 'actor': label, 'reason': label,
                         'snapshot': case['quote']['snapshot']})
    assert response.status_code == 200, response.text
    approved = response.json()
    assert client.get(f"/api/requests/{case['id']}").json() == approved
    row = next(r for r in client.get('/api/inventory').json() if r['product_id'] == 'gonher-gp-149')
    response = raw_post(client, '/api/demo/inventory/gonher-gp-149',
                        {'version': row['version'], 'actor': label, 'reason': label,
                         'price': row['price'], 'cost': row['cost'], 'on_hand': row['on_hand']})
    assert response.status_code == 200, response.text
    assert client.get('/api/inventory/audit').json()[-1]['reason'] == label
    manual = raw_post(client, '/api/requests',
                      {'request_id': 'manual-' + label, 'customer': label, 'message': label,
                       'manual_lines': [{'reference': label, 'quantity': 1}]})
    assert manual.status_code == 201, manual.text
    assert manual.json()['lines'][0]['suggested_reference'] == label
