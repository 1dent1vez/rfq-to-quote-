"""Real loopback HTTP smoke; run after ./run-demo.sh, no mocked responses."""
import json
import re
import sys
import uuid
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'

def http(path, data=None):
    body = urlencode(data).encode() if data is not None else None
    request = Request(base + path, data=body)
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except HTTPError as error:
        return error.code, error.read().decode()

status, html = http('/')
assert status == 200
assert 'Ingreso de refacciones' in html
asset = re.search(r'src="(/assets/[^\"]+\.js)"', html).group(1)
assert http(asset)[0] == 200
catalog_status, body = http('/api/catalog')
assert catalog_status == 200
catalog = json.loads(body)
assert len(catalog) == 8 and all(not product['synthetic'] and product['source']['printed_page'] == 69 for product in catalog)
ref = 'pieza | referencia=GP-149 | cantidad=2'
vehicle = 'vehiculo | descripcion=filtro de aceite | marca=Nissan | modelo=Versa | anio=2021 | motor=1.6 | cantidad=1'
scenarios = [
    ('reference', ref, 'identified'),
    ('vehicle', vehicle, 'identified'),
    ('mixed', ref + '\n' + vehicle, 'identified'),
    ('cabin-alternatives', vehicle.replace('filtro de aceite','filtro de cabina'), 'pending'),
    ('missing-year', vehicle.replace(' | anio=2021', ''), 'pending'),
    ('malformed', 'Mensaje libre no admitido\npieza | referencia=GP-149 | cantidad=NaN', 'pending'),
]
results = []
for name, text, expected in scenarios:
    payload = {'request_id': 'smoke-' + name + '-' + str(uuid.uuid4()), 'customer': 'Taller Rivera (ficticio)', 'email_text': text}
    status, body = http('/api/cases', payload)
    assert status == 201, (name, status, body)
    case = json.loads(body)
    assert case['status'] == expected
    detail_status, detail = http('/api/cases/' + case['id'])
    assert detail_status == 200 and json.loads(detail) == case
    assert http('/api/cases', payload)[0] == 409
    assert case['email_text'] == text
    assert all(p['source'] == next(c['source'] for c in catalog if c['id']==p['id']) for line in case['lines'] for p in line['candidates'])
    results.append({'scenario': name, 'request_id': case['request_id'], 'id': case['id'], 'status': case['status'], 'line_statuses': [line['status'] for line in case['lines']], 'candidates': [len(line['candidates']) for line in case['lines']], 'readback': 'exact', 'duplicate_http_status': 409})
# Exercise the new form transport with real wording, mixed capture and exact readback.
fields = [{'mode':'pieza','referencia':' gp-149 ','cantidad':'2'}, {'mode':'vehiculo','descripcion':'filtro de aceite','marca':'nissan','modelo':'versa','anio':'2021','motor':'1.6','cantidad':'1'}]
payload = {'request_id':'form-smoke-'+str(uuid.uuid4()),'customer':'Servicio Automotriz Los Pinos (ficticio)','email_text':'Dos GP-149.\nY aceite para Versa 2021 1.6.','structured_lines':json.dumps(fields)}
status, body = http('/api/cases',payload)
case = json.loads(body)
assert status == 201 and case['status'] == 'identified'
assert case['email_text'] == payload['email_text'] and case['structured_lines'] == fields
assert all(line['evidence']['source']=='seller_form' for line in case['lines'])
assert json.loads(http('/api/cases/'+case['id'])[1]) == case
assert http('/api/cases',payload)[0] == 409
results.append({'scenario':'structured-mixed','id':case['id'],'status':case['status'],'readback':'exact','original_and_fields_preserved':True,'references':[line['candidates'][0]['reference'] for line in case['lines']]})
list_status, body = http('/api/cases')
assert list_status == 200
persisted = json.loads(body)
assert all(any(case['id'] == result['id'] for case in persisted) for result in results)
assert http('/api/cases', {'request_id':'empty-smoke','customer':'Demo','email_text':' '})[0] == 422
assert http('/api/cases/missing')[0] == 404
assert http('/api/cases/' + results[0]['id'] + '/approve', {})[0] == 404
print(json.dumps({'url': base, 'html_status':200, 'asset_status':200, 'catalog_count':len(catalog), 'source_readback':[{'reference':p['reference'],'source':p['source']} for p in catalog], 'scenarios_verified':len(results), 'cases': results, 'empty_http_status':422, 'unknown_detail_http_status':404, 'commercial_endpoint_http_status':404}, ensure_ascii=False, indent=2))
