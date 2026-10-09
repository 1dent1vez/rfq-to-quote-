"""Local-only quote export; escape untrusted content and spreadsheet formulas."""
import csv
import io
from html import escape


def printable(case):
    quote = case['quote']
    def context(line):
        vehicle = line.get('vehicle')
        return (' '.join(str(vehicle[k]) for k in ('make','model','year','engine'))+' · declaración de catálogo, no garantía') if vehicle else 'Por referencia; compatibilidad vehicular no evaluada'
    rows = ''.join(f"<tr><td>{escape(line['product']['reference'])}</td><td>{escape(line['product']['description'])}<br><small>{escape(context(line))}</small></td><td>{line['quantity']}</td><td>${line['price']}</td><td>${line['line_total']}</td></tr>" for line in quote['lines'])
    return f'''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cotización DEMO</title>
<style>body{{font-family:system-ui;color:#15313b;max-width:900px;margin:48px auto;padding:20px}}header{{border-bottom:4px solid #0e8274}}small{{color:#566}}table{{width:100%;border-collapse:collapse;margin:30px 0}}th,td{{text-align:left;padding:14px;border-bottom:1px solid #ddd}}.total{{font-size:24px;text-align:right}}.notice{{padding:16px;background:#eef6f5}}@media print{{body{{margin:0}}}}</style>
<header><small>RFQ → QUOTE / PORTFOLIO LOCAL</small><h1>Cotización aprobada · DEMO</h1></header>
<p>Cliente ficticio: <strong>{escape(case['customer'])}</strong><br>Solicitud: {escape(case['request_id'])}<br>Versión cotizada: {quote['version']} · aprobó: {escape(case['approval']['actor'])}</p>
<table><thead><tr><th>Referencia GONHER</th><th>Descripción</th><th>Cantidad</th><th>Precio MXN</th><th>Importe MXN</th></tr></thead><tbody>{rows}</tbody></table>
<p class="total">Subtotal ${quote['subtotal']}<br>IVA 16% ${quote['vat']}<br><strong>Total MXN ${quote['total']}</strong></p>
<p class="notice">Precios y existencias sintéticos. IVA 16% es un supuesto DEMO; no es factura ni compromiso comercial. Sin descuentos. Reserva local simulada. No enviado por correo.</p>
<p>Fuente de referencias y aplicaciones: GONHER 2026, página impresa 69 (PDF 71). Consulta por referencia no certifica compatibilidad. Declaración de catálogo, no garantía de instalación.</p>
<small>Snapshot: {quote['snapshot']}<br>Reglas: {escape(quote['rules']['version'])} · margen bruto mínimo 20%</small></html>'''


def spreadsheet(case):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    def safe(value):
        text = str(value)
        return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text
    writer.writerow(['DEMO synthetic quote','customer','request','quote_version','currency'])
    writer.writerow(['Not invoice',safe(case['customer']),safe(case['request_id']),case['quote']['version'],'MXN'])
    writer.writerow(['reference','description','quantity','unit_price','line_total'])
    for line in case['quote']['lines']:
        writer.writerow([safe(line['product']['reference']),safe(line['product']['description']),line['quantity'],line['price'],line['line_total']])
    for key in ('subtotal','vat','total'):
        writer.writerow([key,case['quote'][key]])
    writer.writerow(['VAT assumption','16%','minimum gross margin','20%','no discounts'])
    return '\ufeff'+stream.getvalue()
