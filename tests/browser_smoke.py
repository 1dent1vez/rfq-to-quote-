"""Optional real-browser smoke: pip install playwright; playwright install chromium.
Use CHROMIUM_BIN to reuse a locally installed Chromium. No mocked API responses.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parent.parent
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get('CHROMIUM_BIN'))
    page = browser.new_page(viewport={'width':1280,'height':1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8000/')
    expect(page.get_by_role('heading', name='Ingreso de refacciones', exact=True)).to_be_visible()
    expect(page.get_by_role('region', name='Catálogo GONHER disponible').locator('article')).to_have_count(8)
    results = []
    for sample, status, expected_lines in [('Dos GP-149','Solicitud identificada',1),('Kit Versa 2018','Solicitud pendiente',3),('Versa 2021 aceite','Solicitud identificada',1),('Falta año','Solicitud pendiente',1),('Referencia no cubierta','Solicitud pendiente',1)]:
        page.get_by_role('button', name='Nueva solicitud', exact=True).click()
        page.get_by_role('button', name=sample, exact=True).click()
        request_id = page.get_by_label('Identificador de solicitud', exact=True).input_value()
        original = page.get_by_role('textbox', name='Mensaje original editable', exact=True).input_value()
        page.get_by_role('button', name='Identificar y guardar', exact=True).click()
        region = page.get_by_role('region', name='Resultado de identificación')
        expect(region.get_by_text(status, exact=True)).to_be_visible()
        expect(region.locator('article.line')).to_have_count(expected_lines)
        assert region.locator('details pre').first.text_content() == original, (sample, repr(original), repr(region.locator('details pre').first.text_content()))
        expect(page.get_by_role('button', name='Ver solicitud ' + request_id, exact=True)).to_be_visible()
        if sample == 'Kit Versa 2018':
            expect(region.locator('.candidate')).to_have_count(4)
            expect(region.get_by_text('Campos por confirmar: seleccion', exact=True)).to_be_visible()
            expect(region.get_by_role('link',name='GONHER 2026 · página impresa 69')).to_have_count(4)
            region.screenshot(path=str(root/'docs'/'seller-alternatives.png'))
            # Explicit choice via form; new record preserves the original unresolved request.
            page.get_by_role('button', name='Copiar para aclarar', exact=True).click()
            page.get_by_label('Referencia 3',exact=True).fill('GAF-2271')
            page.get_by_role('button',name='Identificar y guardar',exact=True).click()
            expect(region.get_by_text('Solicitud identificada',exact=True)).to_be_visible()
        if sample == 'Falta año':
            expect(region.get_by_text('Campos por confirmar: anio', exact=True)).to_be_visible()
        results.append({'sample':sample, 'status':status, 'lines':expected_lines, 'original_preserved':True, 'request_id':request_id})
    # Real duplicate error, then persisted list/detail across a browser reload.
    page.get_by_role('button', name='Identificar y guardar', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('Identificador ya registrado')
    page.reload()
    page.get_by_role('button', name='Ver solicitud ' + request_id, exact=True).click()
    expect(page.get_by_role('region', name='Resultado de identificación').get_by_text('Solicitud pendiente', exact=True)).to_be_visible()
    page.screenshot(path=str(root/'docs'/'seller-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(root/'docs'/'seller-mobile.png'),full_page=True)
    assert not errors, errors
    browser.close()
    print(json.dumps({'browser':'local headless Chromium','url':'http://127.0.0.1:8000/','samples_verified':len(results),'cases':results,'duplicate_alert_verified':True,'reload_list_detail_verified':True,'mobile_horizontal_overflow':False,'page_errors':errors,'screenshots':[str(root/'docs'/name) for name in ['seller-desktop.png','seller-mobile.png','seller-alternatives.png']]},ensure_ascii=False,indent=2))
