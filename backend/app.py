"""Block 1: deterministic source-backed catalog intake; fictional transactions. No commercial operations."""
import json
import os
import sqlite3
import uuid
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

SOURCE = {'manufacturer': 'GONHER', 'edition': '2026', 'printed_page': 69, 'pdf_page': 71, 'url': 'https://gonher.com.mx/wp-content/uploads/2026/04/CATALOGO26_FILTROS.pdf'}
CATALOG = []
for start, end, refs in [(2012, 2019, ('GP-149','GA-306','GAC-2271','GAF-2271')), (2020, 2025, ('GP-91','GAD-6554','GAC-2330','GAF-2330'))]:
    claim = f'Nissan VERSA {end} - {start} L4-1.6L; aceite {refs[0]}; aire {refs[1]}; cabina {refs[2]} / {refs[3]}'
    source = {**SOURCE, 'claim': claim, 'scope': 'Curated GP oil subset; GPS not included. Catalog claim, not fitment certification.'}
    for reference, description in zip(refs, ('filtro de aceite','filtro de aire','filtro de cabina','filtro de cabina')):
        CATALOG.append({'id': 'gonher-'+reference.lower(), 'reference': reference, 'manufacturer':'GONHER', 'description': description, 'synthetic':False, 'source':source, 'applications':[{'make':'Nissan','model':'Versa','year':year,'engine':'1.6','source_engine':'L4-1.6L','synthetic':False,'source':source} for year in range(start,end+1)]})

def identify(text, products):
    lines = []
    vehicle_keys = {'descripcion': 'description', 'marca': 'make', 'modelo': 'model', 'anio': 'year', 'motor': 'engine'}
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        tokens = raw.split('|')
        mode = tokens[0].strip().casefold()
        source_backed = any('source' in product for product in products)
        def equal(a, b):
            return str(a).strip().casefold() == str(b).strip().casefold() if source_backed else str(a) == str(b)
        fields, errors = {}, []
        allowed = {'referencia', 'fabricante', 'cantidad'} if mode == 'pieza' else {*vehicle_keys, 'cantidad', 'fabricante', 'referencia'}
        if mode not in ('pieza', 'vehiculo'):
            errors.append('formato')
        for token in tokens[1:]:
            if token.count('=') != 1:
                errors.append('formato')
                continue
            key, value = (part.strip() for part in token.split('=', 1))
            key = key.casefold()
            if key not in allowed or key in fields:
                errors.append('formato')
                continue
            fields[key] = value
        quantity = None
        value = fields.get('cantidad', '')
        if value.isascii() and value.isdigit() and len(value) <= 7 and 1 <= int(value) <= 1000000:
            quantity = int(value)
        else:
            errors.append('cantidad')
        compatibility = 'not_evaluated'
        candidates, missing = [], []
        if 'formato' not in errors and mode == 'vehiculo':
            missing = [key for key in vehicle_keys if not fields.get(key)]
            year = fields.get('anio', '')
            if year and not (year.isascii() and year.isdigit() and len(year) == 4 and 1886 <= int(year) <= 2100):
                errors.append('anio')
            for product in products:
                if fields.get('fabricante') and not equal(product['manufacturer'], fields['fabricante']):
                    continue
                if fields.get('descripcion') and not equal(product['description'], fields['descripcion']):
                    continue
                applications = [application for application in product['applications'] if all(not fields.get(key) or equal(application[attr], fields[key]) for key, attr in vehicle_keys.items() if key != 'descripcion')]
                if fields.get('referencia') and not equal(product['reference'], fields['referencia']):
                    continue
                if applications:
                    candidates.append({**product, 'matching_applications': applications})
            if not missing and len(candidates) > 1:
                missing = ['seleccion'] if source_backed else ['referencia', 'fabricante']
            elif not missing and not candidates:
                missing = list(vehicle_keys)
            elif not missing and not errors:
                compatibility = 'source_catalog_claim_only' if source_backed else 'synthetic_application_only'
        elif 'formato' not in errors and mode == 'pieza':
            candidates = [product for product in products if equal(product['reference'], fields.get('referencia')) and (not fields.get('fabricante') or equal(product['manufacturer'], fields['fabricante']))]
            reference_exists = any(equal(product['reference'], fields.get('referencia')) for product in products)
            missing = ['fabricante'] if len(candidates) > 1 or (not candidates and reference_exists) else ([] if candidates else ['referencia'])
        missing = list(dict.fromkeys(errors + missing))
        clarifications = []
        for field in missing:
            if field == 'formato':
                clarifications.append('Usar pieza o vehiculo y campos clave=valor separados por |; sin claves desconocidas ni repetidas.')
            elif field == 'seleccion':
                clarifications.append('Elegir referencia entre alternativas de cabina GAC/GAF con el cliente; mismo fabricante, referencias distintas, sin selección automática.')
            elif field == 'cantidad':
                clarifications.append('cantidad debe ser un entero de 1 a 1000000; no fracciones, negativos ni valores no finitos.')
            else:
                clarifications.append(f'Confirmar {field} con el cliente; sin selección automática.')
        if not candidates and 'formato' not in errors:
            clarifications.append('Sin cobertura en este subconjunto del catálogo; no demuestra incompatibilidad. Confirmar datos o revisar otra fuente; no hay sustitutos automáticos.')
        lines.append({'mode': mode, 'fields': fields, 'quantity': quantity, 'status': 'pending' if missing else 'matched', 'compatibility': compatibility, 'candidates': candidates, 'missing_fields': missing, 'clarifications': clarifications, 'evidence': {'source': 'message', 'line': number, 'text': raw}})
    return lines

def create_app(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title='Ingreso de refacciones — catálogo GONHER, operaciones ficticias')
    app.state.db_path = str(db_path)
    @contextmanager
    def db():
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()
    with db() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS seller_v2_catalog(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS seller_v2_cases(id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, data TEXT NOT NULL);''')
        for product in CATALOG:
            conn.execute('INSERT OR IGNORE INTO seller_v2_catalog VALUES(?,?)', (product['id'], json.dumps(product)))
    def products(conn):
        return [json.loads(r['data']) for r in conn.execute('SELECT data FROM seller_v2_catalog ORDER BY id')]
    @app.get('/api/catalog')
    def get_catalog():
        with db() as conn:
            return products(conn)
    @app.get('/api/cases')
    def list_cases():
        with db() as conn:
            return [json.loads(r['data']) for r in conn.execute('SELECT data FROM seller_v2_cases ORDER BY rowid DESC')]
    @app.get('/api/cases/{case_id}')
    def get_case(case_id: str):
        with db() as conn:
            row = conn.execute('SELECT data FROM seller_v2_cases WHERE id=?', (case_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Solicitud no encontrada')
            return json.loads(row['data'])
    @app.post('/api/cases', status_code=201)
    def create_case(request_id: str = Form(..., max_length=128), customer: str = Form(..., max_length=200), email_text: str = Form(..., max_length=20000), structured_lines: str | None = Form(None, max_length=20000)):
        if not request_id.strip() or not customer.strip():
            raise HTTPException(422, 'Identificador y cliente no pueden estar vacíos.')
        if not email_text.strip() or len(email_text) > 20000 or len(email_text.splitlines()) > 100:
            raise HTTPException(422, 'Mensaje requerido: máximo 20000 caracteres y 100 líneas.')
        structured = None
        parsed_text = email_text
        if structured_lines is not None:
            try:
                structured = json.loads(structured_lines)
                if not isinstance(structured, list) or not 1 <= len(structured) <= 100:
                    raise ValueError()
                if any(not isinstance(row, dict) or any(not isinstance(k, str) or any(c in k for c in '|=\n\r') or not isinstance(v, str) or '|' in v or '=' in v or '\n' in v or '\r' in v for k, v in row.items()) for row in structured):
                    raise ValueError()
                parsed_text = '\n'.join(row.get('mode','') + ''.join(' | '+k+'='+v for k,v in row.items() if k != 'mode') for row in structured)
            except (ValueError, TypeError):
                raise HTTPException(422, 'Líneas del formulario inválidas; use campos separados.') from None
        with db() as conn:
            lines = identify(parsed_text, products(conn))
            if structured is not None:
                for line in lines:
                    line['evidence']['source'] = 'seller_form'
                    line['evidence']['structured_fields'] = structured[line['evidence']['line']-1]
            case = {'id': str(uuid.uuid4()), 'request_id': request_id, 'customer': customer, 'email_text': email_text, 'extractor': 'deterministic-offline-v1', 'synthetic': True, 'status': 'pending' if any(line['status'] == 'pending' for line in lines) else 'identified', 'lines': lines}
            if structured is not None:
                case['structured_lines'] = structured
                case['extractor'] = 'deterministic-seller-form-v2'
            try:
                conn.execute('INSERT INTO seller_v2_cases VALUES(?,?,?)', (case['id'], request_id, json.dumps(case)))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'Identificador ya registrado. Consulte el historial o use un identificador nuevo.') from None
            return case
    frontend = Path(__file__).resolve().parent.parent / 'frontend' / 'dist'
    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(frontend / 'index.html')
    app.mount('/assets', StaticFiles(directory=frontend / 'assets', check_dir=False), name='assets')
    return app

app = create_app(os.environ.get('RFQ_DB', str(Path(__file__).resolve().parent.parent / 'data' / 'seller-intake-v2.sqlite3')))
