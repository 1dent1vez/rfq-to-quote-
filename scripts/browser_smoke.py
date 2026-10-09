"""Real Chromium + HTTP smoke. Isolated temporary demo DB; never historical stores."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def run():
    with tempfile.TemporaryDirectory(prefix='rfq-browser-') as scratch:
        with socket.socket() as s:
            s.bind(('127.0.0.1',0))
            port = s.getsockname()[1]
        env = {**os.environ,'RFQ_PORTFOLIO_DB':str(Path(scratch)/'portfolio.sqlite3')}
        server = subprocess.Popen([sys.executable,'-m','uvicorn','backend.portfolio:application','--factory','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        url = f'http://127.0.0.1:{port}'
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url+'/api/health',timeout=1) as response:
                        assert json.load(response)['status']=='ok'
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError(server.stderr.read().decode())
                    time.sleep(.05)
            else:
                raise RuntimeError('Local smoke server did not become ready')
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width':1440,'height':1000},locale='es-MX')
                errors = []
                page.on('pageerror',lambda error: errors.append(str(error)))
                page.goto(url)
                expect(page.get_by_role('heading',name='1. Recibir solicitud')).to_be_visible()
                expect(page.get_by_label('Sugerencias offline (no LLM)')).not_to_be_checked()
                screenshots = ROOT/'docs/screenshots'
                screenshots.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=screenshots/'01-intake.png',full_page=True)
                page.get_by_label('Sugerencias offline (no LLM)').check()
                page.get_by_label('Identificador',exact=True).fill('portfolio-browser-demo')
                page.get_by_role('button',name='Recibir solicitud',exact=True).click()
                expect(page.get_by_role('heading',name='2. Revisión humana')).to_be_visible()
                expect(page.get_by_label('Referencia revisada 1')).to_have_value('')
                expect(page.get_by_role('button',name='Crear borrador',exact=True)).to_be_disabled()
                page.get_by_label('Referencia revisada 1').select_option('gonher-gp-149')
                page.get_by_label('Actor demo',exact=True).fill('Vendedor demo')
                page.get_by_label('Motivo de revisión / aprobación').fill('Confirmación ficticia del alcance del pedido')
                page.get_by_label('Clasificación fragmento 1').select_option('resolved_context')
                page.get_by_label('Motivo fragmento 1').fill('Entrega local confirmada, sin promesa de plazo')
                page.get_by_label('Evidencia suplementaria nueva').fill('Cliente ficticio confirma dos GP-149 por referencia y entrega local, sin fecha prometida.')
                page.screenshot(path=screenshots/'02-review.png',full_page=True)
                page.get_by_role('button',name='Guardar revisión y evidencia').click()
                expect(page.get_by_role('button',name='Crear borrador',exact=True)).to_be_enabled()
                page.get_by_role('button',name='Crear borrador',exact=True).click()
                expect(page.get_by_role('heading',name='3. Cotización borrador · v3')).to_be_visible()
                expect(page.get_by_label('Cotización').get_by_text('Total MXN $348.00',exact=True)).to_be_visible()
                page.get_by_label('Acepto la versión',exact=False).check()
                page.get_by_role('button',name='Aprobar y reservar DEMO').click()
                expect(page.get_by_role('heading',name='4. Aprobada · reserva local registrada')).to_be_visible()
                expect(page.get_by_label('Referencia revisada 1')).to_be_disabled()
                stock_row = page.get_by_role('table',name='Inventario DEMO').get_by_role('row').filter(has=page.get_by_role('cell',name='GP-149',exact=True))
                expect(stock_row.get_by_role('cell').nth(4)).to_have_text('2')
                expect(stock_row.get_by_role('cell').nth(5)).to_have_text('18')
                page.screenshot(path=screenshots/'03-approved.png',full_page=True)
                with page.expect_download() as item:
                    page.get_by_role('link',name='Descargar HTML imprimible').click()
                html = item.value
                html.save_as(Path(scratch)/'quote.html')
                content = (Path(scratch)/'quote.html').read_text()
                assert '348.00' in content and 'Cotización aprobada' in content
                with page.expect_download() as item:
                    page.get_by_role('link',name='Descargar CSV',exact=True).click()
                item.value.save_as(Path(scratch)/'quote.csv')
                assert 'GP-149' in (Path(scratch)/'quote.csv').read_text()
                quote_page = browser.new_page()
                quote_page.goto((Path(scratch)/'quote.html').as_uri())
                quote_page.screenshot(path=screenshots/'04-printable.png',full_page=True)
                page.reload()
                page.get_by_role('button',name='Taller Rivera (ficticio)',exact=False).click()
                expect(page.get_by_role('heading',name='4. Aprobada · reserva local registrada')).to_be_visible()
                # Real CSV transport through browser (new synthetic request).
                page.get_by_label('Identificador',exact=True).fill('portfolio-csv-demo')
                page.get_by_label('Adjunto TXT/CSV').set_input_files({'name':'request.csv','mimeType':'text/csv','buffer':b'reference,quantity\nGP-149,1\nGA-306,1\n'})
                page.get_by_role('button',name='Recibir solicitud',exact=True).click()
                expect(page.get_by_label('Referencia revisada 2')).to_be_visible()
                page.get_by_label('Actor demo',exact=True).fill('Revisor CSV')
                page.get_by_label('Motivo de revisión / aprobación').fill('Validar transporte CSV sintético')
                page.get_by_label('Referencia revisada 1').select_option('gonher-gp-149')
                page.get_by_label('Referencia revisada 2').select_option('gonher-ga-306')
                page.get_by_label('Clasificación fragmento 1').select_option('requested_part')
                page.get_by_label('Motivo fragmento 1').fill('CSV contiene dos artículos vinculados por captura de líneas')
                page.get_by_label('Línea del fragmento 1').select_option('0')
                page.get_by_label('Evidencia suplementaria nueva').fill('Cliente demo confirma ambos artículos CSV y cantidades originales, consulta por referencia.')
                page.get_by_role('button',name='Guardar revisión y evidencia').click()
                expect(page.get_by_role('button',name='Crear borrador',exact=True)).to_be_enabled()
                page.get_by_role('button',name='Crear borrador',exact=True).click()
                expect(page.get_by_role('button',name='Aprobar y reservar DEMO')).to_be_visible()
                # Reprice after draft; real operator UI must make approval stale.
                page.get_by_text('Operador DEMO · inventario y reinicio',exact=True).click()
                page.get_by_label('Artículo operativo').select_option('gonher-gp-149')
                page.get_by_label('Actor operador').fill('Operador demo')
                page.get_by_label('Motivo operativo').fill('Reproducir cambio de precio posterior al borrador')
                page.get_by_label('Precio DEMO MXN').fill('160.00')
                page.get_by_role('button',name='Guardar inventario DEMO').click()
                expect(page.get_by_role('status')).to_contain_text('Inventario demo actualizado')
                page.get_by_label('Acepto la versión',exact=False).check()
                page.get_by_role('button',name='Aprobar y reservar DEMO').click()
                expect(page.get_by_role('alert')).to_contain_text('regenere borrador')
                expect(page.get_by_role('link',name='Descargar CSV',exact=True)).to_have_count(0)
                page.screenshot(path=screenshots/'05-stale-draft.png',full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                page.get_by_role('heading',name='2. Revisión humana').scroll_into_view_if_needed()
                page.screenshot(path=screenshots/'06-mobile.png',full_page=False)
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile overflow'
                assert not errors, errors
                browser.close()
                print(json.dumps({'browser':'Chromium','real_http':True,'flows':['offline review → draft → approve → HTML/CSV download','reload persistence','CSV attachment intake and review','operator price edit → stale approval rejected','mobile no horizontal overflow'],'screenshots':6,'page_errors':errors}))
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__=='__main__':
    run()
