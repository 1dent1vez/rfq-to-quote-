import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { request } from './portfolio-api'
import Operations from './Operations'
import type { Case, Product, Resolution, FragmentReview } from './portfolio-types'
const statuses={pending:'Pendiente de revisión',reviewed:'Revisada',draft:'Borrador',approved:'Aprobada'}
type EditableFragment=Omit<FragmentReview,'kind'>&{kind:FragmentReview['kind']|''}
const mxn=(value:string)=>new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'}).format(Number(value))

export default function Portfolio(){
 const [customer,setCustomer]=useState('Taller Rivera (ficticio)')
 const [message,setMessage]=useState('2 GP-149; entrega urgente')
 const [requestId,setRequestId]=useState<string>(()=>crypto.randomUUID())
 const [suggestions,setSuggestions]=useState(false)
 const [manual,setManual]=useState([{reference:'GP-149',quantity:'2'}])
 const [file,setFile]=useState<File|null>(null)
 const [catalog,setCatalog]=useState<Product[]>([])
 const [history,setHistory]=useState<Case[]>([])
 const [value,setValue]=useState<Case|null>(null)
 const [lines,setLines]=useState<Resolution[]>([])
 const [fragments,setFragments]=useState<EditableFragment[]>([])
 const [actor,setActor]=useState('')
 const [reason,setReason]=useState('')
 const [supplement,setSupplement]=useState('')
 const [accepted,setAccepted]=useState(false)
 const [dirty,setDirty]=useState(false)
 const [error,setError]=useState('')
 const [busy,setBusy]=useState(false)
 async function refresh(){setHistory(await request<Case[]>('/api/requests'))}
 useEffect(()=>{request<Product[]>('/api/catalog').then(setCatalog).catch(e=>setError(e.message));refresh().catch(e=>setError(e.message))},[])
 function load(c:Case){setValue(c);setLines(c.lines.map(line=>line.resolution??{id:line.id,product_id:'',quantity:line.suggested_quantity??0,scope:'reference',vehicle:null}));setFragments(c.fragments.map(f=>f.classification??{id:f.id,kind:'',reason:'',line_id:null}));setAccepted(false);setDirty(false);setSupplement('')}
 function editLine(index:number,change:Partial<Resolution>){setDirty(true);setAccepted(false);setLines(lines.map((r,i)=>i===index?{...r,...change}:r))}
 function editFragment(index:number,change:Partial<EditableFragment>){setDirty(true);setAccepted(false);setFragments(fragments.map((r,i)=>i===index?{...r,...change}:r))}
 async function mutate(action:'review'|'draft'|'approve'){
  if(!value)return
  await task(async()=>{
   const extra=action==='review'?{supplement,lines,fragments}:action==='approve'?{snapshot:value.quote?.snapshot}:{}
   const result=await request<Case>(`/api/requests/${value.id}/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version:value.version,actor,reason,...extra})})
   load(result);await refresh()
  })
 }
 async function task(action:()=>Promise<void>){setError('');setBusy(true);try{await action()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function submit(e:FormEvent){e.preventDefault();await task(async()=>{
  let result:Case
  if(file){
   if(file.size>20000||!(/\.(txt|csv)$/i.test(file.name)))throw new Error('Adjunto: solo TXT/CSV UTF-8, máximo 20000 bytes.')
   const body=new FormData();body.set('request_id',requestId);body.set('customer',customer);body.set('suggestions',String(suggestions));body.set('file',file)
   result=await request<Case>('/api/attachments',{method:'POST',body})
  }else result=await request<Case>('/api/requests',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:requestId,customer,message,suggestions,manual_lines:suggestions?[]:manual.map(r=>({reference:r.reference,quantity:r.quantity?Number(r.quantity):null}))})})
  load(result);await refresh()
 })}
 return <main className="portfolio">
  <header className="hero"><span className="eyebrow">RFQ → QUOTE / DEMO LOCAL</span><h1>De solicitud a cotización.<br/><em>Con revisión humana.</em></h1><p>Catálogo con fuente. Evidencia intacta. Aprobación explícita.</p><p className="notice">Clientes, precios, costos y existencias sintéticos · Sin IA activa, sin envío de correo · Identidades demo, no autenticación de producción.</p></header>
  <nav aria-label="Etapas"><span>01 Recibir</span><span>02 Revisar</span><span>03 Cotizar</span><span>04 Aprobar y descargar</span></nav>
  {error&&<p role="alert" className="error">{error}</p>}
  <div className="workspace"><section className="panel"><h2>1. Recibir solicitud</h2><form onSubmit={submit}><fieldset disabled={busy}>
   <label>Identificador<input required maxLength={128} value={requestId} onChange={e=>setRequestId(e.target.value)}/></label>
   <label>Cliente ficticio<input required maxLength={200} value={customer} onChange={e=>setCustomer(e.target.value)}/></label>
   <label>Mensaje original<textarea rows={4} required={!file} maxLength={20000} value={message} onChange={e=>setMessage(e.target.value)}/></label>
   <label>Adjunto TXT/CSV<input type="file" accept=".txt,.csv" onChange={e=>setFile(e.target.files?.[0]??null)}/></label><small>UTF-8 estricto · 20000 bytes · 100 líneas. CSV: reference,quantity. El adjunto es la evidencia de entrada cuando se selecciona.</small>
   <label className="check"><input type="checkbox" checked={suggestions} onChange={e=>setSuggestions(e.target.checked)}/>Sugerencias offline (no LLM)</label><small>Opt-in: solo referencias explícitas y cantidades numéricas locales. No interpreta contexto ni asigna vehículos.</small>
   {!suggestions&&!file&&<><h3>Captura manual inicial</h3>{manual.map((r,i)=><div className="row" key={i}><label>Referencia inicial {i+1}<input value={r.reference} onChange={e=>setManual(manual.map((x,n)=>n===i?{...x,reference:e.target.value}:x))}/></label><label>Cantidad inicial {i+1}<input type="number" min="1" max="1000000" value={r.quantity} onChange={e=>setManual(manual.map((x,n)=>n===i?{...x,quantity:e.target.value}:x))}/></label></div>)}<button type="button" onClick={()=>setManual([...manual,{reference:'',quantity:''}])} disabled={manual.length>=100}>Agregar artículo inicial</button></>}
   <div className="actions"><button className="primary" type="submit">{busy?'Procesando…':'Recibir solicitud'}</button><button type="button" onClick={()=>{setValue(null);setRequestId(crypto.randomUUID());setError('')}}>Nueva solicitud</button></div>
  </fieldset></form></section>
  <aside className="panel history"><h2>Historial local</h2><p>SQLite persistente · solo datos demo.</p>{history.length===0?<p>Sin solicitudes todavía.</p>:history.map(c=><button disabled={busy} key={c.id} onClick={()=>task(async()=>load(await request<Case>('/api/requests/'+c.id)))}>{c.customer}<small>{c.request_id} · {statuses[c.status]} · v{c.version}</small></button>)}</aside></div>
  {value&&<section className="panel" aria-label="Solicitud activa"><div className="section-title"><h2>2. Revisión humana</h2><span className={'status '+value.status}>{statuses[value.status]} · v{value.version}</span><button disabled={busy} onClick={()=>task(async()=>load(await request<Case>('/api/requests/'+value.id)))}>Recargar versión guardada</button></div><p>{value.customer} · {value.request_id}</p>
   <div className="evidence"><h3>Evidencia original · inmutable</h3><pre>{value.original.message}</pre>{value.original.attachment&&<small>Adjunto: {value.original.attachment.filename} · UTF-8</small>}</div>
   <p>Las sugerencias nunca son aprobaciones. Seleccione cada referencia. Datos faltantes y aclaraciones se registran como evidencia nueva, no se reescribe el original.</p>
   <fieldset disabled={busy||value.status==='approved'} className="review-fields">
    <div className="row"><label>Actor demo<input maxLength={100} value={actor} onChange={e=>setActor(e.target.value)}/></label><label>Motivo de revisión / aprobación<input maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)}/></label></div>
    {lines.map((r,i)=>{const source=value.lines.find(x=>x.id===r.id);const product=catalog.find(p=>p.id===r.product_id);return <article className="line-card" key={r.id}><h3>Artículo {i+1} <small>ID {r.id}</small></h3><small>{source?.resolution?'Línea resuelta por revisión humana':'Línea pendiente de revisión'}</small><p>Sugerencia no aprobada: {source?.suggested_reference??'captura humana'} · cantidad {source?.suggested_quantity??'pendiente'}</p><details><summary>Evidencia de línea</summary><pre>{JSON.stringify(source?.evidence??[],null,2)}</pre></details>
     <div className="row"><label>Referencia revisada {i+1}<select value={r.product_id} onChange={e=>editLine(i,{product_id:e.target.value})}><option value="">Elegir explícitamente</option>{catalog.map(p=><option key={p.id} value={p.id}>{p.reference} · {p.description}</option>)}</select></label><label>Cantidad revisada {i+1}<input type="number" min="1" max="1000000" value={r.quantity||''} onChange={e=>editLine(i,{quantity:Number(e.target.value)})}/></label><label>Alcance {i+1}<select value={r.scope} onChange={e=>editLine(i,{scope:e.target.value as Resolution['scope'],vehicle:e.target.value==='vehicle'?{make:'',model:'',year:0,engine:''}:null})}><option value="reference">Por referencia, sin certificar vehículo</option><option value="vehicle">Por vehículo, verificar fuente</option></select></label></div>
     {r.scope==='vehicle'&&<div className="row">{(['make','model','year','engine'] as const).map(key=><label key={key}>{({make:'Marca',model:'Modelo',year:'Año',engine:'Motor'})[key]} revisado {i+1}<input type={key==='year'?'number':'text'} value={r.vehicle?.[key]||''} onChange={e=>editLine(i,{vehicle:{...(r.vehicle??{make:'',model:'',year:0,engine:''}),[key]:key==='year'?Number(e.target.value):e.target.value}})}/></label>)}</div>}
     {product&&<p className="source"><a href={product.source.url} target="_blank" rel="noreferrer">GONHER {product.source.edition} · página impresa {product.source.printed_page}</a> · Nissan Versa {product.applications[0].year}–{product.applications.at(-1)?.year} L4-1.6L. Declaración de catálogo, no garantía. No se elige alternativa de cabina automáticamente.</p>}
    </article>})}
    <button disabled={lines.length>=100} onClick={()=>{setDirty(true);setAccepted(false);setLines([...lines,{id:'human-'+crypto.randomUUID(),product_id:'',quantity:0,scope:'reference',vehicle:null}])}}>Agregar artículo de evidencia suplementaria</button>
    <h3>Fragmentos sin procesar · clasificación obligatoria</h3><p>Si un fragmento contiene otro artículo, agréguelo y vincúlelo. Si contiene restricciones o datos de vehículo, confirme su alcance en la evidencia suplementaria. Solo saludos sin contenido pueden clasificarse no sustantivos.</p>
    {fragments.map((f,i)=><article key={f.id} className="fragment"><blockquote>{value.fragments[i]?.text}</blockquote><small>Original [{value.fragments[i]?.start}, {value.fragments[i]?.end})</small><div className="row"><label>Clasificación fragmento {i+1}<select value={f.kind} onChange={e=>editFragment(i,{kind:e.target.value as EditableFragment['kind']})}><option value="">Pendiente</option><option value="non_substantive">Saludo / no sustantivo</option><option value="resolved_context">Contexto sustantivo confirmado</option><option value="requested_part">Artículo solicitado</option></select></label><label>Motivo fragmento {i+1}<input value={f.reason} maxLength={1000} onChange={e=>editFragment(i,{reason:e.target.value})}/></label>{f.kind==='requested_part'&&<label>Línea del fragmento {i+1}<select value={f.line_id??''} onChange={e=>editFragment(i,{line_id:e.target.value||null})}><option value="">Vincular artículo</option>{lines.map((line,n)=><option key={line.id} value={line.id}>Artículo {n+1}</option>)}</select></label>}</div></article>)}
    <label>Evidencia suplementaria nueva<textarea rows={3} maxLength={20000} value={supplement} onChange={e=>{setSupplement(e.target.value);setDirty(true);setAccepted(false)}} placeholder="Confirmación ficticia del cliente: cantidades, vehículo y restricciones confirmadas…"/></label>
    <div className="actions"><button className="primary" disabled={actor.trim().length<3||reason.trim().length<5||supplement.trim().length<5||!lines.length||lines.some(r=>!r.product_id||r.quantity<1)||fragments.some(f=>!f.kind||f.reason.trim().length<5||(f.kind==='requested_part'&&!f.line_id))} onClick={()=>mutate('review')}>Guardar revisión y evidencia</button><button disabled={dirty||value.status==='pending'||actor.trim().length<3||reason.trim().length<5} onClick={()=>mutate('draft')}>Crear borrador</button></div>
    {dirty&&<p className="notice">Cambios sin guardar: guarde revisión y evidencia antes de cotizar o aprobar.</p>}
   </fieldset>
   {value.quote&&<section className="quote" aria-label="Cotización"><h2>3. Cotización {value.status==='approved'?'aprobada':'borrador'} · v{value.quote.version}</h2><p>DEMO · MXN · IVA 16% supuesto · margen bruto mínimo 20% · sin descuentos</p><div className="table-scroll"><table><thead><tr><th>Referencia</th><th>Cantidad</th><th>Precio MXN</th><th>Importe MXN</th></tr></thead><tbody>{value.quote.lines.map(r=><tr key={r.line_id}><td>{r.product.reference}<small>{r.product.description}</small></td><td>{r.quantity}</td><td>{mxn(r.price)}</td><td>{mxn(r.line_total)}</td></tr>)}</tbody></table></div><div className="totals"><span>Subtotal {mxn(value.quote.subtotal)}</span><span>IVA 16% {mxn(value.quote.vat)}</span><strong>Total MXN {mxn(value.quote.total)}</strong></div><details><summary>Versión de reglas y snapshot aprobado</summary><p>Reglas: {value.quote.rules.version}</p><p className="hash">Snapshot: {value.quote.snapshot}</p><p className="hash">Catálogo: {value.quote.catalog_hash}</p><p>Precios, costos y stock sintéticos. Los costos y márgenes internos se incluyen en el snapshot, no en la descarga para cliente.</p></details>
    {value.status==='draft'&&<><label className="check"><input disabled={busy||dirty} type="checkbox" checked={accepted} onChange={e=>setAccepted(e.target.checked)}/>Acepto la versión {value.quote.version}, reglas y catálogo mostrados; reservar stock DEMO</label><button className="primary" disabled={busy||dirty||!accepted||actor.trim().length<3||reason.trim().length<5} onClick={()=>mutate('approve')}>Aprobar y reservar DEMO</button><p>Se revalida disponibilidad, margen y precios en una transacción SQLite. No se envía correo.</p></>}
    {value.status==='approved'&&<div className="approved"><h3>4. Aprobada · reserva local registrada</h3><p>Solo lectura. No es factura ni compromiso comercial.</p><div className="actions"><a className="button primary" download href={`/api/requests/${value.id}/download.html`}>Descargar HTML imprimible</a><a className="button" download href={`/api/requests/${value.id}/download.csv`}>Descargar CSV</a></div><small>Abra el HTML y use Imprimir / Guardar como PDF del navegador. No generador PDF ni OCR.</small></div>}
   </section>}
   <details open><summary>Evidencia suplementaria y auditoría persistente</summary>{value.supplements.map((s,i)=><blockquote key={i}>v{s.version} · {s.actor}: {s.text}<small>{s.reason}</small></blockquote>)}<ol className="audit">{value.audit.map((event,i)=><li key={i}><strong>{event.action}</strong><span> v{event.version} · {event.actor} · {new Date(event.at).toLocaleString('es-MX')}</span><p>{event.reason}</p></li>)}</ol></details>
  </section>}
  <Operations catalog={catalog} refreshToken={`${value?.id??''}:${value?.version??0}`} onChange={()=>setAccepted(false)} onReset={()=>{setValue(null);setRequestId(crypto.randomUUID());setAccepted(false);refresh().catch(e=>setError(e.message))}}/>
  <footer>RFQ → QUOTE · Portfolio offline. IA experimental solo CLI opt-in, no lista para este flujo. Sin inferencias ni reinicio de presupuestos.</footer>
 </main>
}
