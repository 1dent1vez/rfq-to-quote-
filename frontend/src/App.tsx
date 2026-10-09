import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { IntakeCase, Product } from './types'
import CaseView from './CaseView'
import { request } from './api'

type SellerLine = Record<string, string>
const initial: SellerLine = {mode:'pieza',referencia:'GP-149',cantidad:'2'}

const vehicle = (description='filtro de aceite',year='2018'): SellerLine => ({mode:'vehiculo',descripcion:description,marca:'Nissan',modelo:'Versa',anio:year,motor:'1.6',cantidad:'1'})
export const samples = [
 {name:'Dos GP-149',customer:'Taller Rivera (ficticio)',message:'Necesito dos filtros GP-149.',rows:[initial]},
 {name:'Kit Versa 2018',customer:'Servicio Automotriz Los Pinos (ficticio)',message:'Un kit de aceite, aire y cabina para Nissan Versa 2018 1.6.',rows:[vehicle(),vehicle('filtro de aire'),vehicle('filtro de cabina')]},
 {name:'Versa 2021 aceite',customer:'Refaccionaria Ruta Norte (ficticio)',message:'Filtro de aceite para Versa 2021 1.6, una pieza.',rows:[vehicle('filtro de aceite','2021')]},
 {name:'Falta año',customer:'Mecánica Integral El Roble (ficticio)',message:'Un filtro de aceite para Versa 1.6; falta confirmar el año.',rows:[vehicle('filtro de aceite','')]},
 {name:'Referencia no cubierta',customer:'Autotaller La Estación (ficticio)',message:'Solicitan una referencia fuera del subconjunto: NO-CUBIERTA.',rows:[{mode:'pieza',referencia:'NO-CUBIERTA',cantidad:'1'}]},
]
export default function App() {
  const [message, setMessage] = useState('Necesito dos filtros GP-149.')
  const [requestId, setRequestId] = useState<string>(() => crypto.randomUUID())
  const [customer, setCustomer] = useState('Taller Rivera (ficticio)')
  const [rows, setRows] = useState<SellerLine[]>([initial])
  const [legacy, setLegacy] = useState(false)
  function edit(index: number, key: string, value: string) { setRows(rows.map((row,i) => i === index ? {...row,[key]:value} : row)) }
  const [result, setResult] = useState<IntakeCase | null>(null)
  const [history, setHistory] = useState<IntakeCase[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [catalog, setCatalog] = useState<Product[]>([])
  useEffect(() => {
    request<Product[]>('/api/catalog').then(setCatalog).catch(err => setError((err as Error).message))
  }, [])
  async function refreshHistory() {
    try { setHistory(await request<IntakeCase[]>('/api/cases')) }
    catch (err) { setError((err as Error).message) }
  }
  useEffect(() => { void refreshHistory() }, [])
  async function openCase(id: string) {
    setError('')
    setResult(null)
    try { setResult(await request<IntakeCase>('/api/cases/' + id)) }
    catch (err) { setError((err as Error).message) }
  }
  function newRequest() {
    setRequestId(crypto.randomUUID())
    setResult(null)
    setError('')
  }
  function copyForClarification() {
    if (!result) return
    setMessage(result.email_text)
    setRows(result.structured_lines ?? [initial])
    setLegacy(!result.structured_lines)
    setCustomer(result.customer)
    newRequest()
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    setResult(null)
    // URL encoding preserves literal LF; multipart FormData normalizes it to CRLF.
    const body = new URLSearchParams()
    body.set('request_id', requestId)
    body.set('customer', customer)
    body.set('email_text', message)
    if (!legacy) body.set('structured_lines', JSON.stringify(rows))
    try {
      setResult(await request<IntakeCase>('/api/cases', {method: 'POST', body}))
      await refreshHistory()
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  return <main>
    <header><span>Bloque 1 · Punto de revisión humana</span><h1>Ingreso de refacciones</h1>
      <p>Baseline determinista offline · No es un LLM</p>
      <p>Catálogo GONHER 2026 · Declaraciones del fabricante, no garantía de compatibilidad. Clientes y transacciones ficticios.</p>
    </header>
    {error && <p role="alert" className="error">{error}</p>}
    <section aria-labelledby="intake-heading"><h2 id="intake-heading">1. Mensaje original</h2>
      <button disabled={busy} onClick={newRequest}>Nueva solicitud</button>
      
      <div>{samples.map(sample=><button key={sample.name} disabled={busy} onClick={()=>{newRequest();setLegacy(false);setMessage(sample.message);setCustomer(sample.customer);setRows(sample.rows)}}>{sample.name}</button>)}</div>
      <form onSubmit={submit}>
        <label>Identificador de solicitud<input disabled={busy} required maxLength={128} value={requestId} onChange={event => setRequestId(event.target.value)} /></label>
        <label>Cliente ficticio<input disabled={busy} required maxLength={200} value={customer} onChange={event => setCustomer(event.target.value)} /></label>
        <label>Mensaje original editable<textarea disabled={busy} required maxLength={20000} rows={7} value={message} onChange={event => setMessage(event.target.value)} /></label>
        <p>No interpreta lenguaje natural. El mensaje se conserva; el vendedor captura los campos por separado.</p>
        {!legacy && rows.map((row,index) => <fieldset disabled={busy} key={index}><legend>Artículo {index+1}</legend>
          {row.mode === 'vehiculo' && <>
            <label>Marca {index+1}<input value={row.marca} onChange={e=>edit(index,'marca',e.target.value)} /></label>
            <label>Modelo {index+1}<input value={row.modelo} onChange={e=>edit(index,'modelo',e.target.value)} /></label>
            <label>Año {index+1}<input value={row.anio} onChange={e=>edit(index,'anio',e.target.value)} /></label>
            <label>Motor {index+1}<input value={row.motor} onChange={e=>edit(index,'motor',e.target.value)} /></label>
            <label>Tipo de filtro {index+1}<select value={row.descripcion} onChange={e=>edit(index,'descripcion',e.target.value)}>{['filtro de aceite','filtro de aire','filtro de cabina'].map(type=><option key={type}>{type}</option>)}</select></label>
          </>}
          <label>Referencia {index+1}<input value={row.referencia ?? ''} onChange={e=>edit(index,'referencia',e.target.value)} /></label>
          <label>Cantidad {index+1}<input value={row.cantidad} onChange={e=>edit(index,'cantidad',e.target.value)} /></label>
        </fieldset>)}
        {!legacy && <div><button type="button" disabled={busy || rows.length>=100} onClick={()=>setRows([...rows,{mode:'pieza',referencia:'',cantidad:'1'}])}>Agregar referencia</button><button type="button" disabled={busy || rows.length>=100} onClick={()=>setRows([...rows,vehicle('filtro de aceite','')])}>Agregar vehículo</button></div>}
        <details><summary>Avanzado: entrada técnica heredada (opcional)</summary>
          <label><input type="checkbox" checked={legacy} onChange={e=>setLegacy(e.target.checked)} />Usar gramática técnica en el mensaje</label>
          <p>pieza | referencia=GP-149 | cantidad=2. vehiculo: descripcion, marca, modelo, anio, motor, cantidad; referencia opcional para elegir alternativa. Sin campos duplicados. Identificadores: tolera espacios externos y mayúsculas, no repara guiones.</p>
        </details>
        <button disabled={busy} className="primary" type="submit">{busy ? 'Guardando…' : 'Identificar y guardar'}</button>
      </form>
    </section>
    <section aria-label="Catálogo GONHER disponible" className="catalog">
      <h2>Catálogo GONHER disponible</h2>
      <p>Subconjunto curado: Nissan Versa 2012–2025 L4-1.6L, filtros GP de aceite, aire y cabina. GPS no incluido. Sin precios ni existencias.</p>
      <div className="catalog-grid">{catalog.map(product => <article key={product.id}>
        <strong>{product.reference}</strong> <span className="badge">Fuente fabricante</span>
        <p>{product.description} · {product.manufacturer}</p>
        <small>Registro: {product.id}</small>
        <p>Nissan Versa · {product.applications[0]?.year}–{product.applications.at(-1)?.year} · L4-1.6L</p>
        {product.source && <a href={product.source.url}>GONHER {product.source.edition} · página impresa {product.source.printed_page}</a>}
      </article>)}</div>
    </section>
    <section aria-label="Historial persistido"><h2>Historial local · SQLite</h2>
      {history.length === 0 && <p>Sin solicitudes guardadas.</p>}
      <ul>{history.map(item => <li key={item.id}>
        <button disabled={busy} onClick={() => void openCase(item.id)} aria-label={'Ver solicitud ' + item.request_id}>{item.request_id} · {item.customer} · {item.status === 'pending' ? 'Pendiente' : 'Identificada'}</button>
      </li>)}</ul>
    </section>
    {result && <><button onClick={copyForClarification}>Copiar para aclarar</button><CaseView value={result} /></>}
  </main>
}
