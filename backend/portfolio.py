"""Isolated offline portfolio workflow. Demo identities are not authentication."""
import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import csv
import io
import re
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .deterministic import parse_message

from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {'manufacturer':'GONHER','edition':'2026','printed_page':69,'pdf_page':71,'url':'https://gonher.com.mx/wp-content/uploads/2026/04/CATALOGO26_FILTROS.pdf'}
CATALOG = []
for start,end,refs in [(2012,2019,('GP-149','GA-306','GAC-2271','GAF-2271')),(2020,2025,('GP-91','GAD-6554','GAC-2330','GAF-2330'))]:
    for reference,description in zip(refs,('filtro de aceite','filtro de aire','filtro de cabina','filtro de cabina')):
        CATALOG.append({'id':'gonher-'+reference.lower(),'reference':reference,'manufacturer':'GONHER','description':description,'source':{**SOURCE,'scope':'Catalog claim only; not fitment certification. GP subset, excludes GPS.'},'applications':[{'make':'Nissan','model':'Versa','year':y,'engine':'1.6','source_engine':'L4-1.6L'} for y in range(start,end+1)]})

def _safe_text(value):
    """Reject non-scalar Unicode before validation errors, hashing or persistence."""
    if isinstance(value, str):
        try:
            value.encode('utf-8', errors='strict')
        except UnicodeEncodeError:
            # Do not echo the invalid input: JSON error rendering also uses UTF-8.
            raise HTTPException(422, 'Texto requiere Unicode válido codificable en UTF-8') from None
    elif isinstance(value, dict):
        for key, item in value.items():
            _safe_text(key)
            _safe_text(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _safe_text(item)


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True)

    @model_validator(mode='before')
    @classmethod
    def unicode_scalar_fields(cls, value):
        _safe_text(value)
        return value

    @model_validator(mode='after')
    def substantive_audit_fields(self):
        for field,minimum in (('actor',3),('reason',5),('supplement',5)):
            value = getattr(self,field,None)
            if value is not None and len(value.strip())<minimum:
                raise ValueError('Actor, motivo y evidencia suplementaria requieren contenido sustantivo')
        return self

class Mutation(Strict):
    version: int = Field(ge=1)
    actor: str = Field(min_length=3,max_length=100)
    reason: str = Field(min_length=5,max_length=1000)

class Vehicle(Strict):
    make: str = Field(min_length=1,max_length=60)
    model: str = Field(min_length=1,max_length=60)
    year: int = Field(ge=1886,le=2100)
    engine: str = Field(min_length=1,max_length=30)

class Resolution(Strict):
    id: str = Field(min_length=1,max_length=100)
    product_id: str
    quantity: int = Field(ge=1,le=1000000)
    scope: Literal['reference','vehicle']
    vehicle: Vehicle | None = None

class Classification(Strict):
    id: str
    kind: Literal['non_substantive','resolved_context','requested_part']
    reason: str = Field(min_length=5,max_length=1000)
    line_id: str | None = None

class Review(Mutation):
    supplement: str = Field(min_length=5,max_length=20000)
    lines: list[Resolution] = Field(min_length=1,max_length=100)
    fragments: list[Classification] = Field(max_length=300)


from decimal import Decimal, ROUND_HALF_UP
from collections import Counter

RULES = {'version':'demo-commercial-v1','currency':'MXN','vat_rate':'0.16','minimum_gross_margin':'0.20','discounts':'none','tax_scope':'Demo assumption, not tax advice','data_scope':'Prices, costs and stock are synthetic, not manufacturer facts'}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def money(value):
    return format(value.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP),'.2f')

class Approval(Mutation):
    snapshot: str = Field(min_length=1,max_length=64)

class InventoryEdit(Mutation):
    price: str = Field(pattern=r'^[0-9]{1,7}\.[0-9]{2}$')
    cost: str = Field(pattern=r'^[0-9]{1,7}\.[0-9]{2}$')
    on_hand: int = Field(ge=0,le=1000000)

from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from .quote_export import printable, spreadsheet
from urllib.parse import urlparse

class Reset(Strict):
    confirmation: Literal['RESET PORTFOLIO DEMO']
    actor: str = Field(min_length=3,max_length=100)
    reason: str = Field(min_length=5,max_length=1000)

class Manual(Strict):
    reference: str = Field(max_length=100)
    quantity: int | None = Field(default=None,ge=1,le=1000000)

class Intake(Strict):
    request_id: str = Field(min_length=1, max_length=128)
    customer: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=20000)
    suggestions: bool = False
    manual_lines: list[Manual] = Field(default_factory=list,max_length=100)


def create_app(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title='RFQ to quote · DEMO offline')
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','[::1]','testserver'])
    @app.middleware('http')
    async def safety(request,call_next):
        response = None
        if request.method in ('POST','PUT','PATCH','DELETE'):
            origin = request.headers.get('origin')
            if origin and urlparse(origin).netloc != request.headers.get('host'):
                response = JSONResponse({'detail':'Solo solicitudes del mismo origen local'},status_code=403)
            else:
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body)>65536:
                        response = JSONResponse({'detail':'Entrada excede 65536 bytes'},status_code=413)
                        break
                if response is None:
                    request._body = bytes(body)
        if response is None:
            response = await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        return response
    @contextmanager
    def db():
        conn = sqlite3.connect(path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
    with db() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables - {'portfolio_cases','portfolio_meta','portfolio_inventory','portfolio_inventory_audit'}:
            raise ValueError('Refusing non-portfolio database')
        conn.execute('CREATE TABLE IF NOT EXISTS portfolio_cases(id TEXT PRIMARY KEY, request_id TEXT UNIQUE, fingerprint TEXT, data TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS portfolio_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        conn.execute("INSERT OR IGNORE INTO portfolio_meta VALUES('schema','portfolio-v1')")
        conn.execute('CREATE TABLE IF NOT EXISTS portfolio_inventory(product_id TEXT PRIMARY KEY,price TEXT,cost TEXT,on_hand INTEGER,reserved INTEGER,version INTEGER)')
        conn.execute('CREATE TABLE IF NOT EXISTS portfolio_inventory_audit(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
        for i,p in enumerate(CATALOG):
            conn.execute('INSERT OR IGNORE INTO portfolio_inventory VALUES(?,?,?,?,0,1)',(p['id'],money(Decimal(150+i*25)),money(Decimal(90+i*15)),20))

    @app.get('/api/health')
    def health():
        return {'status':'ok','schema':'portfolio-v1','inference_enabled':False,'identity':'local demo, not production authentication'}

    @app.get('/api/requests')
    def history():
        with db() as conn:
            return [json.loads(r['data']) for r in conn.execute('SELECT data FROM portfolio_cases ORDER BY rowid DESC')]

    @app.get('/api/requests/{case_id}')
    def get_case(case_id: str):
        with db() as conn:
            row = conn.execute('SELECT data FROM portfolio_cases WHERE id=?',(case_id,)).fetchone()
            if not row:
                raise HTTPException(404,'Solicitud no encontrada')
            return json.loads(row['data'])

    def create_intake(payload: Intake, attachment=None):
        if not payload.request_id.strip() or not payload.customer.strip() or not payload.message.strip() or len(payload.message.splitlines()) > 100 or any(ord(c)<32 and c not in '\n\r\t' for c in payload.message):
            raise HTTPException(422,'Entrada vacía, binaria o mayor a 100 líneas')
        original = payload.model_dump()
        if attachment:
            original['attachment'] = attachment
        fingerprint = hashlib.sha256(json.dumps(original,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with db() as conn:
            previous = conn.execute('SELECT * FROM portfolio_cases WHERE request_id=?',(payload.request_id,)).fetchone()
            if previous:
                if previous['fingerprint'] != fingerprint:
                    raise HTTPException(409,'Identificador reutilizado con contenido distinto')
                return json.loads(previous['data'])
            try:
                parsed = parse_message(payload.message) if payload.suggestions else None
            except ValueError:
                raise HTTPException(422,'Parser offline: máximo 100 referencias; use captura manual si necesita aclaración') from None
            items = (parsed['result'] or {}).get('items',[]) if parsed else []
            lines = [{'id':str(i),'suggested_reference':item['reference']['value'], 'suggested_quantity':(item.get('quantity') or {}).get('value'),'evidence':item['reference']['evidence'],'resolution':None} for i,item in enumerate(items)]
            if payload.manual_lines:
                lines = [{'id':str(i),'suggested_reference':r.reference,'suggested_quantity':r.quantity,'evidence':[{'source':'manual_intake','row':i+1,'reference':r.reference,'quantity':r.quantity}],'resolution':None} for i,r in enumerate(payload.manual_lines)]
            for line in lines:
                line['status']='pending'
            fragments = parsed['unresolved_fragments'] if parsed else [{'start':0,'end':len(payload.message),'text':payload.message}]
            case = {'id':str(uuid.uuid4()),'request_id':payload.request_id,'customer':payload.customer,'original':original,'version':1,'status':'pending','lines':lines,'fragments':[{**f,'id':str(i),'classification':None} for i,f in enumerate(fragments)],'parser':parsed,'supplements':[],'audit':[{'action':'received','actor':'demo-intake','reason':'Solicitud sintética local','version':1,'at':datetime.now(timezone.utc).isoformat()}],'quote':None}
            conn.execute('INSERT INTO portfolio_cases VALUES(?,?,?,?)',(case['id'],payload.request_id,fingerprint,json.dumps(case,ensure_ascii=False)))
            return case
    @app.post('/api/requests',status_code=201)
    def intake(payload: Intake):
        if payload.manual_lines and payload.suggestions:
            raise HTTPException(422,'Elija captura manual o sugerencias, no ambas')
        return create_intake(payload)

    @app.post('/api/attachments',status_code=201)
    async def attachment(file: UploadFile = File(...), request_id: str = Form(...,max_length=128), customer: str = Form(...,max_length=200), suggestions: bool = Form(False)):
        name = file.filename or ''
        if not re.fullmatch(r'[A-Za-z0-9_ .-]{1,100}\.(txt|csv)',name,re.I) or '..' in name:
            raise HTTPException(422,'Nombre seguro requerido; solo TXT/CSV UTF-8')
        raw = await file.read(20001)
        if len(raw) > 20000:
            raise HTTPException(422,'Adjunto excede 20000 bytes')
        try:
            text = raw.decode('utf-8-sig',errors='strict')
        except UnicodeDecodeError:
            raise HTTPException(422,'Adjunto requiere codificación UTF-8 estricta') from None
        if not text.strip() or '\x00' in text or any(ord(c)<32 and c not in '\n\r\t' for c in text) or len(text.splitlines()) > 100:
            raise HTTPException(422,'Adjunto vacío, binario o mayor a 100 líneas')
        manual = []
        if name.lower().endswith('.csv'):
            try:
                rows = list(csv.reader(io.StringIO(text),strict=True))
                if not rows or rows[0] != ['reference','quantity'] or not 1 <= len(rows)-1 <= 99:
                    raise ValueError()
                for row in rows[1:]:
                    if len(row) != 2 or not re.fullmatch(r'[A-Za-z]{2,4}-?[0-9]{2,5}',row[0]) or (row[1] and not re.fullmatch(r'[0-9]{1,7}',row[1])):
                        raise ValueError()
                    manual.append(Manual(reference=row[0],quantity=int(row[1]) if row[1] else None))
            except (ValueError,csv.Error):
                raise HTTPException(422,'CSV: encabezado reference,quantity; referencias literales y cantidades enteras positivas') from None
        payload = Intake(request_id=request_id,customer=customer,message=text,suggestions=suggestions and not manual,manual_lines=manual)
        return create_intake(payload,{'filename':name,'text':text,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'encoding':'UTF-8'})

    def load(conn, case_id):
        row = conn.execute('SELECT data FROM portfolio_cases WHERE id=?',(case_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Solicitud no encontrada')
        return json.loads(row['data'])

    def save(conn, case, payload, action):
        case['version'] += 1
        case['audit'].append({'action':action,'actor':payload.actor,'reason':payload.reason,'version':case['version'],'at':datetime.now(timezone.utc).isoformat()})
        conn.execute('UPDATE portfolio_cases SET data=? WHERE id=?',(json.dumps(case,ensure_ascii=False),case['id']))
        return case

    def check(case,payload):
        if case['version'] != payload.version:
            raise HTTPException(409,'Versión obsoleta; recargue la solicitud')
        if case['status'] == 'approved':
            raise HTTPException(409,'Solicitud aprobada: solo lectura')
        if not payload.actor.strip() or not payload.reason.strip():
            raise HTTPException(422,'Actor y motivo requeridos')

    @app.get('/api/catalog')
    def catalog():
        return CATALOG

    @app.post('/api/requests/{case_id}/review')
    def human_review(case_id: str,payload: Review):
        with db() as conn:
            case = load(conn,case_id)
            check(case,payload)
            ids = [r.id for r in payload.lines]
            fragment_ids = [f.id for f in payload.fragments]
            if len(ids) != len(set(ids)) or not {r['id'] for r in case['lines']}.issubset(ids):
                raise HTTPException(422,'No elimine ni duplique artículos solicitados')
            if len(fragment_ids) != len(set(fragment_ids)) or set(fragment_ids) != {f['id'] for f in case['fragments']}:
                raise HTTPException(422,'Clasifique explícitamente cada fragmento original')
            for fragment in payload.fragments:
                literal = next(f['text'] for f in case['fragments'] if f['id']==fragment.id).strip(' \t\r\n,;.!?').casefold()
                if fragment.kind=='non_substantive' and literal not in {'hola','gracias','buen día','buen dia','buenos días','buenos dias','buenas tardes','saludos'}:
                    raise HTTPException(422,'Contenido sustantivo requiere resolución explícita, no saludo')
                if not fragment.reason.strip() or (fragment.kind == 'requested_part' and fragment.line_id not in ids):
                    raise HTTPException(422,'El artículo del fragmento debe vincularse a una línea revisada')
            for resolution in payload.lines:
                product = next((p for p in CATALOG if p['id'] == resolution.product_id),None)
                if not product:
                    raise HTTPException(422,'Referencia fuera del catálogo; no se permiten sustitutos inventados')
                if resolution.scope == 'vehicle':
                    if not resolution.vehicle or resolution.vehicle.model_dump() not in [{k:a[k] for k in ('make','model','year','engine')} for a in product['applications']]:
                        raise HTTPException(422,'Vehículo incompleto o sin declaración en el subconjunto de fuente')
                elif resolution.vehicle:
                    raise HTTPException(422,'Consulta por referencia no certifica compatibilidad de vehículo')
            old = {line['id']:line for line in case['lines']}
            case['lines'] = [{**old.get(r.id,{'id':r.id,'evidence':[],'suggested_reference':None,'suggested_quantity':None}),'resolution':r.model_dump(),'status':'resolved'} for r in payload.lines]
            classifications = {f.id:f.model_dump() for f in payload.fragments}
            case['fragments'] = [{**f,'classification':classifications[f['id']]} for f in case['fragments']]
            case['supplements'].append({'text':payload.supplement,'actor':payload.actor,'reason':payload.reason,'version':case['version']+1,'lines':[r.model_dump() for r in payload.lines],'fragments':[f.model_dump() for f in payload.fragments]})
            case['status'] = 'reviewed'
            case['quote'] = None
            return save(conn,case,payload,'human_review')
    def inventory_rows(conn):
        return [{**dict(r),'available':r['on_hand']-r['reserved'],'synthetic':True} for r in conn.execute('SELECT * FROM portfolio_inventory ORDER BY product_id')]

    def inventory_audit(conn,payload,action,before,after,case_id=None):
        event = {'action':action,'actor':payload.actor,'reason':payload.reason,'before':before,'after':after,'case_id':case_id,'at':datetime.now(timezone.utc).isoformat()}
        conn.execute('INSERT INTO portfolio_inventory_audit VALUES(?,?)',(str(uuid.uuid4()),json.dumps(event)))

    @app.get('/api/inventory')
    def get_inventory():
        with db() as conn:
            return inventory_rows(conn)

    @app.get('/api/inventory/audit')
    def get_inventory_audit():
        with db() as conn:
            return [json.loads(r['data']) for r in conn.execute('SELECT data FROM portfolio_inventory_audit ORDER BY rowid')]

    @app.post('/api/demo/inventory/{product_id}')
    def edit_inventory(product_id: str,payload: InventoryEdit):
        with db() as conn:
            row = conn.execute('SELECT * FROM portfolio_inventory WHERE product_id=?',(product_id,)).fetchone()
            if not row:
                raise HTTPException(404,'Artículo no encontrado')
            before = dict(row)
            if payload.version != row['version']:
                raise HTTPException(409,'Inventario obsoleto; recargue')
            if not payload.actor.strip() or not payload.reason.strip() or Decimal(payload.price)<=0 or payload.on_hand<row['reserved']:
                raise HTTPException(422,'Precio positivo, actor, motivo y existencias >= reservas requeridos')
            conn.execute('UPDATE portfolio_inventory SET price=?,cost=?,on_hand=?,version=version+1 WHERE product_id=?',(payload.price,payload.cost,payload.on_hand,product_id))
            after = dict(conn.execute('SELECT * FROM portfolio_inventory WHERE product_id=?',(product_id,)).fetchone())
            inventory_audit(conn,payload,'demo_inventory_edit',before,after)
            return {**after,'available':after['on_hand']-after['reserved'],'synthetic':True}

    def build_quote(conn,case):
        if not case['lines'] or any(not line['resolution'] for line in case['lines']) or any(not f['classification'] for f in case['fragments']):
            raise HTTPException(422,'Revisión humana incompleta; artículos o contexto pendientes')
        rows = {r['product_id']:r for r in inventory_rows(conn)}
        needed = Counter()
        quote_lines = []
        subtotal = Decimal('0')
        for line in case['lines']:
            resolution = line['resolution']
            product = next((p for p in CATALOG if p['id']==resolution['product_id']),None)
            if not product or resolution['product_id'] not in rows:
                raise HTTPException(422,'Catálogo o inventario desconocido')
            row = rows[product['id']]
            price,cost = Decimal(row['price']),Decimal(row['cost'])
            if not price.is_finite() or not cost.is_finite() or price<=0 or cost<0 or (price-cost)/price < Decimal(RULES['minimum_gross_margin']):
                raise HTTPException(422,'Margen bruto menor al 20% o precio/costo inválido; no hay descuentos')
            qty = resolution['quantity']
            needed[product['id']] += qty
            total = price*qty
            subtotal += total
            quote_lines.append({'line_id':line['id'],'product':product,'quantity':qty,'price':money(price),'cost':money(cost),'gross_margin':format((price-cost)/price,'.4f'),'line_total':money(total),'inventory_snapshot':row,'scope':resolution['scope'],'vehicle':resolution['vehicle']})
        if any(qty>rows[pid]['available'] for pid,qty in needed.items()):
            raise HTTPException(422,'Existencias insuficientes (se suman referencias repetidas)')
        vat = subtotal*Decimal(RULES['vat_rate'])
        quote = {'request':{'id':case['id'],'request_id':case['request_id'],'customer':case['customer'],'review_version':case['supplements'][-1]['version'],'evidence_hash':digest({'original':case['original'],'supplements':case['supplements']})},'lines':quote_lines,'rules':RULES,'catalog_hash':digest(CATALOG),'subtotal':money(subtotal),'vat':money(vat),'total':money(subtotal+Decimal(money(vat))),'synthetic':True}
        quote['snapshot'] = digest(quote)
        return quote

    @app.post('/api/requests/{case_id}/draft')
    def draft(case_id: str,payload: Mutation):
        with db() as conn:
            case = load(conn,case_id)
            check(case,payload)
            case['quote'] = {**build_quote(conn,case),'version':case['version']+1}
            case['status'] = 'draft'
            return save(conn,case,payload,'draft_created')

    @app.post('/api/requests/{case_id}/approve')
    def approve(case_id: str,payload: Approval):
        with db() as conn:
            case = load(conn,case_id)
            quote = case['quote']
            if case['status']=='approved':
                if quote['version']==payload.version and quote['snapshot']==payload.snapshot and case['approval']['actor']==payload.actor and case['approval']['reason']==payload.reason:
                    return case
                raise HTTPException(409,'Aprobación repetida distinta o versión obsoleta')
            check(case,payload)
            if case['status']!='draft' or not quote or quote['version']!=payload.version or quote['snapshot']!=payload.snapshot:
                raise HTTPException(409,'Borrador exacto requerido para aprobación')
            try:
                current = build_quote(conn,case)
            except HTTPException:
                raise HTTPException(409,'Cambió disponibilidad o margen; revise y regenere borrador') from None
            if current['snapshot'] != quote['snapshot']:
                raise HTTPException(409,'Cambió precio, inventario, catálogo o reglas; regenere borrador')
            needed = Counter()
            for line in quote['lines']:
                needed[line['product']['id']] += line['quantity']
            for pid,qty in needed.items():
                before = dict(conn.execute('SELECT * FROM portfolio_inventory WHERE product_id=?',(pid,)).fetchone())
                changed = conn.execute('UPDATE portfolio_inventory SET reserved=reserved+?,version=version+1 WHERE product_id=? AND on_hand-reserved>=?',(qty,pid,qty))
                if changed.rowcount != 1:
                    raise HTTPException(409,'Existencias insuficientes al reservar')
                after = dict(conn.execute('SELECT * FROM portfolio_inventory WHERE product_id=?',(pid,)).fetchone())
                inventory_audit(conn,payload,'demo_reservation',before,after,case_id)
            case['status']='approved'
            case['approval']={'actor':payload.actor,'reason':payload.reason,'quote_version':payload.version,'snapshot':payload.snapshot}
            return save(conn,case,payload,'quote_approved')
    @app.get('/api/requests/{case_id}/download.{format}')
    def download(case_id: str,format: str):
        if format not in ('html','csv'):
            raise HTTPException(422,'Solo HTML imprimible o CSV; PDF/OCR no incluido')
        with db() as conn:
            case = load(conn,case_id)
            if case['status']!='approved':
                raise HTTPException(409,'Descarga habilitada solo tras aprobación humana')
            content = printable(case) if format=='html' else spreadsheet(case)
            return Response(content,media_type='text/html' if format=='html' else 'text/csv',headers={'Content-Disposition':f'attachment; filename="demo-quote-{case["id"]}.{format}"'})

    @app.post('/api/demo/reset')
    def reset(payload: Reset):
        with db() as conn:
            marker = conn.execute("SELECT value FROM portfolio_meta WHERE key='schema'").fetchone()
            if not marker or marker[0]!='portfolio-v1' or not payload.actor.strip() or not payload.reason.strip():
                raise HTTPException(422,'Solo base de datos portfolio-v1 y actor/motivo explícitos')
            before = {'cases':conn.execute('SELECT count(*) FROM portfolio_cases').fetchone()[0],'inventory':inventory_rows(conn)}
            conn.execute('DELETE FROM portfolio_cases')
            for i,p in enumerate(CATALOG):
                conn.execute('UPDATE portfolio_inventory SET price=?,cost=?,on_hand=20,reserved=0,version=version+1 WHERE product_id=?',(money(Decimal(150+i*25)),money(Decimal(90+i*15)),p['id']))
            inventory_audit(conn,payload,'demo_reset',before,{'cases':0,'inventory':inventory_rows(conn)})
            return {'reset':True,'scope':'portfolio-v1 only; historical studies untouched'}

    frontend = ROOT/'frontend/dist'
    @app.get('/',include_in_schema=False)
    def index():
        if not (frontend/'index.html').exists():
            raise HTTPException(503,'Frontend no construido; ejecute run-demo.sh')
        return FileResponse(frontend/'index.html')
    app.mount('/assets',StaticFiles(directory=frontend/'assets',check_dir=False),name='assets')
    return app


def application():
    return create_app(os.environ.get('RFQ_PORTFOLIO_DB',str(ROOT/'data/portfolio-v1.sqlite3')))

