import importlib
import copy


def receive(client, **changes):
    payload = {'request_id':'demo-review','customer':'Taller ficticio','message':'2 GP-149; entrega urgente','suggestions':True}
    return client.post('/api/requests',json={**payload,**changes}).json()


def review(case, **changes):
    return {'version':case['version'],'actor':'Vendedor demo','reason':'Cliente confirma alcance y entrega local',
            'supplement':'Confirmado: dos GP-149 por referencia; entrega local sin promesa de plazo.',
            'lines':[{'id':'0','product_id':'gonher-gp-149','quantity':2,'scope':'reference','vehicle':None}],
            'fragments':[{'id':f['id'],'kind':'resolved_context','reason':'Entrega local acordada, sin promesa de plazo','line_id':None} for f in case['fragments']], **changes}


def test_human_review_is_new_evidence_and_blocks_unresolved_context(tmp_path):
    client = TestClient(factory(tmp_path/'portfolio.sqlite3'))
    case = receive(client)
    original = copy.deepcopy(case['original'])
    bad = review(case,fragments=[])
    assert client.post(f"/api/requests/{case['id']}/review",json=bad).status_code == 422
    revised = client.post(f"/api/requests/{case['id']}/review",json=review(case))
    assert revised.status_code == 200, revised.text
    revised = revised.json()
    assert revised['version'] == 2 and revised['status'] == 'reviewed'
    assert revised['lines'][0]['status'] == 'resolved'
    assert revised['original'] == original and revised['supplements'][0]['text']
    assert revised['audit'][-1]['actor'] == 'Vendedor demo'
    assert client.post(f"/api/requests/{case['id']}/review",json=review(case)).status_code == 409
    assert client.get('/api/catalog').json()[0]['source']['printed_page'] == 69


def test_vehicle_scope_never_invents_fitment(tmp_path):
    client = TestClient(factory(tmp_path/'portfolio.sqlite3'))
    case = receive(client)
    line = {'id':'0','product_id':'gonher-gp-149','quantity':1,'scope':'vehicle','vehicle':{'make':'Nissan','model':'Versa','year':2023,'engine':'1.6'}}
    assert client.post(f"/api/requests/{case['id']}/review",json=review(case,lines=[line])).status_code == 422
    line['vehicle']['year'] = 2018
    assert client.post(f"/api/requests/{case['id']}/review",json=review(case,lines=[line])).status_code == 200


def test_review_cannot_drop_requested_lines_or_forge_original(tmp_path):
    client = TestClient(factory(tmp_path/'portfolio.sqlite3'))
    case = receive(client,message='2 GP-149; 1 GA-306')
    assert client.post(f"/api/requests/{case['id']}/review",json=review(case)).status_code == 422
    assert client.post(f"/api/requests/{case['id']}/review",json={**review(case),'original':{}}).status_code == 422
from fastapi.testclient import TestClient


def factory(path):
    spec = importlib.util.find_spec('backend.portfolio')
    assert spec is not None, 'Integrated portfolio API is missing'
    return importlib.import_module('backend.portfolio').create_app(path)


def test_attachment_utf8_csv_and_manual_intake(tmp_path):
    client = TestClient(factory(tmp_path/'portfolio.sqlite3'))
    csv = b'reference,quantity\nGP-149,2\nGA-306,1\n'
    result = client.post('/api/attachments',data={'request_id':'csv-1','customer':'Demo CSV','suggestions':'false'},files={'file':('request.csv',csv,'text/csv')})
    assert result.status_code == 201, result.text
    case = result.json()
    assert case['original']['attachment']['text'] == csv.decode()
    assert case['original']['attachment']['filename'] == 'request.csv'
    assert len(case['lines']) == 2 and case['lines'][0]['suggested_reference'] == 'GP-149'
    manual = client.post('/api/requests',json={'request_id':'manual','customer':'Demo','message':'Pedido confirmado por teléfono','manual_lines':[{'reference':'GP-91','quantity':None}]})
    assert manual.status_code == 201 and manual.json()['lines'][0]['suggested_quantity'] is None


def test_attachments_reject_binary_oversize_bad_csv_and_traversal_names(tmp_path):
    client = TestClient(factory(tmp_path/'portfolio.sqlite3'))
    for name,content in [('x.pdf',b'pdf'),('x.txt',b'\xff'),('x.txt',b'a'*20001),('x.txt',b'a\x00b'),('../../x.txt',b'2 GP-149'),('x.csv',b'reference,quantity\nGP-149,2,extra'),('x.csv',b'reference,quantity\n=CMD(),2')]:
        response = client.post('/api/attachments',data={'request_id':'bad','customer':'Demo'},files={'file':(name,content)})
        assert response.status_code == 422, (name,response.text)
    assert client.get('/api/requests').json() == []


def draft(client,case):
    return client.post(f"/api/requests/{case['id']}/draft",json={'version':case['version'],'actor':'Vendedor demo','reason':'Revisión comercial explícita'})


def approved_payload(case):
    return {'version':case['version'],'actor':'Supervisor demo','reason':'Acepto versión, catálogo y reglas mostradas','snapshot':case['quote']['snapshot']}


def resolved(client,**changes):
    case = receive(client,**changes)
    return client.post(f"/api/requests/{case['id']}/review",json=review(case)).json()


def test_decimal_draft_exact_approval_reserves_once_persists_and_readonly(tmp_path):
    path = tmp_path/'portfolio.sqlite3'
    client = TestClient(factory(path))
    pending = receive(client)
    assert draft(client,pending).status_code == 422
    case = client.post(f"/api/requests/{pending['id']}/review",json=review(pending)).json()
    response = draft(client,case)
    assert response.status_code == 200, response.text
    case = response.json()
    assert case['quote']['subtotal'] == '300.00'
    assert case['quote']['vat'] == '48.00' and case['quote']['total'] == '348.00'
    assert case['quote']['rules']['minimum_gross_margin'] == '0.20'
    approval = approved_payload(case)
    approved = client.post(f"/api/requests/{case['id']}/approve",json=approval)
    assert approved.status_code == 200, approved.text
    approved = approved.json()
    assert approved['status'] == 'approved'
    stock = {r['product_id']:r for r in client.get('/api/inventory').json()}
    assert stock['gonher-gp-149']['reserved'] == 2 and stock['gonher-gp-149']['available'] == 18
    assert client.post(f"/api/requests/{case['id']}/approve",json=approval).json() == approved
    assert client.get('/api/inventory').json() == list(stock.values())
    assert draft(client,approved).status_code == 409
    assert client.post(f"/api/requests/{case['id']}/review",json=review(approved)).status_code == 409
    restarted = TestClient(factory(path))
    assert restarted.get(f"/api/requests/{case['id']}").json() == approved
    assert len(restarted.get('/api/inventory/audit').json()) == 1


def edit_inventory(client,**changes):
    row = next(r for r in client.get('/api/inventory').json() if r['product_id']=='gonher-gp-149')
    return client.post('/api/demo/inventory/gonher-gp-149',json={'version':row['version'],'actor':'Operador demo','reason':'Reproducir cambio de inventario sintético','price':row['price'],'cost':row['cost'],'on_hand':row['on_hand'],**changes})


def test_stale_quote_stock_margin_price_rules_snapshot_block_approval(tmp_path):
    client = TestClient(factory(tmp_path/'portfolio.sqlite3'))
    case = draft(client,resolved(client)).json()
    assert client.post(f"/api/requests/{case['id']}/approve",json={**approved_payload(case),'snapshot':'forged'}).status_code == 409
    assert client.post(f"/api/requests/{case['id']}/approve",json={**approved_payload(case),'version':1}).status_code == 409
    assert edit_inventory(client,price='160.00').status_code == 200
    assert client.post(f"/api/requests/{case['id']}/approve",json=approved_payload(case)).status_code == 409
    case = draft(client,case).json()
    assert case['quote']['total']=='371.20'
    assert edit_inventory(client,on_hand=1).status_code == 200
    assert client.post(f"/api/requests/{case['id']}/approve",json=approved_payload(case)).status_code == 409
    assert draft(client,case).status_code == 422
    assert edit_inventory(client,on_hand=20,cost='159.00').status_code == 200
    assert draft(client,case).status_code == 422
    assert client.get('/api/inventory/audit').json()[-1]['reason']
    assert edit_inventory(client,price='NaN').status_code == 422
    assert edit_inventory(client,price='-1.00').status_code == 422


def test_concurrent_approvals_aggregate_duplicate_lines_no_oversell(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    client = TestClient(factory(tmp_path/'portfolio.sqlite3'))
    edit_inventory(client,on_hand=2)
    one = draft(client,resolved(client,request_id='one')).json()
    two = draft(client,resolved(client,request_id='two')).json()
    def approve(case):
        return client.post(f"/api/requests/{case['id']}/approve",json=approved_payload(case)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(approve,[one,two]))
    assert statuses == [200,409]
    row = next(r for r in client.get('/api/inventory').json() if r['product_id']=='gonher-gp-149')
    assert row['reserved']==2 and row['available']==0
    three = receive(client,request_id='three',message='1 GP-149; 2 GP-149')
    payload = review(three,lines=[{'id':str(i),'product_id':'gonher-gp-149','quantity':q,'scope':'reference','vehicle':None} for i,q in enumerate([1,2])])
    three = client.post(f"/api/requests/{three['id']}/review",json=payload).json()
    edit_inventory(client,on_hand=4)
    assert draft(client,three).status_code == 422


def test_exports_escape_html_spreadsheet_protection_only_approved(tmp_path):
    client = TestClient(factory(tmp_path/'portfolio.sqlite3'))
    case = resolved(client,customer='=SUM(1,2)<script>alert(1)</script>')
    assert client.get(f"/api/requests/{case['id']}/download.html").status_code == 409
    case = draft(client,case).json()
    approved = client.post(f"/api/requests/{case['id']}/approve",json=approved_payload(case)).json()
    html = client.get(f"/api/requests/{case['id']}/download.html")
    assert html.status_code == 200 and '<script>alert(1)</script>' not in html.text
    assert '&lt;script&gt;' in html.text and '348.00' in html.text
    assert 'attachment;' in html.headers['content-disposition']
    csv = client.get(f"/api/requests/{case['id']}/download.csv")
    assert csv.status_code==200 and "'=SUM" in csv.text and 'GP-149' in csv.text
    assert client.get(f"/api/requests/{case['id']}/download.pdf").status_code==422
    assert client.get(f"/api/requests/{case['id']}").json()==approved


def test_isolation_reset_guard_security_headers_unknown_and_malformed(tmp_path):
    import sqlite3
    old = tmp_path/'old.sqlite3'
    with sqlite3.connect(old) as conn:
        conn.execute('CREATE TABLE old_ledger(x INTEGER)')
    import pytest
    with pytest.raises(ValueError,match='non-portfolio'):
        factory(old)
    client = TestClient(factory(tmp_path/'portfolio.sqlite3'))
    receive(client)
    assert client.get('/api/requests/missing').status_code==404
    assert client.post('/api/requests',content='{',headers={'Content-Type':'application/json'}).status_code==422
    assert client.get('/api/health').headers['x-content-type-options']=='nosniff'
    assert 'frame-ancestors' in client.get('/api/health').headers['content-security-policy']
    assert client.post('/api/demo/reset',json={'confirmation':'RESET','actor':'Demo','reason':'Reset synthetic demonstration'}).status_code==422
    assert client.post('/api/demo/reset',json={'confirmation':'RESET PORTFOLIO DEMO','actor':'Demo','reason':'Reset synthetic demonstration'}).status_code==200
    assert client.get('/api/requests').json()==[]
    assert client.get('/api/inventory/audit').json()[-1]['action']=='demo_reset'
    with sqlite3.connect(old) as conn:
        assert conn.execute('SELECT count(*) FROM old_ledger').fetchone()[0]==0


def test_substantive_context_cannot_be_discarded_as_a_greeting(tmp_path):
    client = TestClient(factory(tmp_path/'portfolio.sqlite3'))
    case = receive(client)
    payload = review(case)
    payload['fragments'][0]['kind']='non_substantive'
    assert client.post(f"/api/requests/{case['id']}/review",json=payload).status_code==422
    case = receive(client,request_id='hello',message='Hola; 2 GP-149')
    payload = review(case)
    payload['fragments'][0]['kind']='non_substantive'
    assert client.post(f"/api/requests/{case['id']}/review",json=payload).status_code==200


def test_local_origin_body_limits_and_host_rebinding_protection(tmp_path):
    client = TestClient(factory(tmp_path/'portfolio.sqlite3'))
    assert client.get('/api/health',headers={'host':'evil.example'}).status_code==400
    assert client.post('/api/requests',json={},headers={'origin':'https://evil.example'}).status_code==403
    assert client.post('/api/requests',content=b'x'*65537).status_code==413


def test_actor_reason_supplement_and_context_must_be_substantive(tmp_path):
    client=TestClient(factory(tmp_path/'portfolio.sqlite3'))
    case=receive(client)
    for field in ('actor','reason','supplement'):
        assert client.post(f"/api/requests/{case['id']}/review",json=review(case,**{field:'     x'})).status_code==422
    payload=review(case)
    payload['fragments'][0]['reason']='     x'
    assert client.post(f"/api/requests/{case['id']}/review",json=payload).status_code==422


def test_vehicle_scope_export_includes_only_confirmed_source_claim(tmp_path):
    client=TestClient(factory(tmp_path/'portfolio.sqlite3'))
    case=receive(client,message='1 GP-149 para Versa 2018')
    payload=review(case,lines=[{'id':'0','product_id':'gonher-gp-149','quantity':1,'scope':'vehicle','vehicle':{'make':'Nissan','model':'Versa','year':2018,'engine':'1.6'}}])
    case=client.post(f"/api/requests/{case['id']}/review",json=payload).json()
    case=draft(client,case).json()
    client.post(f"/api/requests/{case['id']}/approve",json=approved_payload(case))
    content=client.get(f"/api/requests/{case['id']}/download.html").text
    assert 'Nissan Versa 2018' in content and '1.6' in content
    assert 'declaración de catálogo' in content.lower()


def test_quote_snapshot_is_bound_to_the_exact_customer_request_evidence(tmp_path):
    client=TestClient(factory(tmp_path/'portfolio.sqlite3'))
    one=draft(client,resolved(client,request_id='one',customer='Taller Uno ficticio')).json()
    two=draft(client,resolved(client,request_id='two',customer='Taller Dos ficticio')).json()
    assert one['quote']['snapshot'] != two['quote']['snapshot']
    assert one['quote']['request']['id']==one['id']
    assert client.post(f"/api/requests/{two['id']}/approve",json=approved_payload(one)).status_code==409


def test_parser_bounds_and_strict_invalid_fields_fail_closed_without_500(tmp_path):
    client=TestClient(factory(tmp_path/'portfolio.sqlite3'))
    for changes in ({'message':' '.join(['GP-149']*101)}, {'suggestions':'yes'}, {'manual_lines':[{'reference':'GP-149','quantity':True}]}, {'message':'a\x01b'}):
        assert client.post('/api/requests',json={'request_id':'bad','customer':'Demo','message':'2 GP-149','suggestions':True,**changes}).status_code==422
    assert client.get('/api/requests').json()==[]


def test_supported_100_line_intake_can_review_all_literal_fragments(tmp_path):
    client=TestClient(factory(tmp_path/'portfolio.sqlite3'))
    case=receive(client,message='\n'.join(['hola 1 GP-149 gracias']*100))
    assert len(case['fragments'])==200
    payload=review(case,lines=[{'id':str(i),'product_id':'gonher-gp-149','quantity':1,'scope':'reference','vehicle':None} for i in range(100)],fragments=[{'id':f['id'],'kind':'non_substantive','reason':'Saludo literal','line_id':None} for f in case['fragments']])
    result=client.post(f"/api/requests/{case['id']}/review",json=payload)
    assert result.status_code==200,result.text


def test_intake_preserves_original_and_idempotency(tmp_path):
    client = TestClient(factory(tmp_path/'portfolio.sqlite3'))
    payload = {'request_id':'demo-1', 'customer':'Taller ficticio', 'message':'2 GP-149; entrega urgente', 'suggestions':True}
    first = client.post('/api/requests',json=payload)
    assert first.status_code == 201
    case = first.json()
    assert case['original']['message'] == payload['message']
    assert case['version'] == 1 and case['status'] == 'pending'
    assert case['lines'][0]['suggested_reference'] == 'GP-149'
    assert case['lines'][0]['status'] == 'pending'
    assert case['fragments']
    assert client.post('/api/requests',json=payload).json()['id'] == case['id']
    assert len(client.get('/api/requests').json()) == 1
    changed = {**payload,'message':'otro texto'}
    assert client.post('/api/requests',json=changed).status_code == 409
    assert client.get('/api/requests/'+case['id']).json() == case
    assert client.get('/api/health').json()['inference_enabled'] is False
