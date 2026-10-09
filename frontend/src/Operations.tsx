import { useEffect, useState } from 'react'
import { request } from './portfolio-api'
import type { Product, Inventory } from './portfolio-types'

type Event={action:string;actor:string;reason:string;at:string;before:unknown;after:unknown}
export default function Operations({catalog,onChange,onReset,refreshToken}:{catalog:Product[];onChange:()=>void;onReset:()=>void;refreshToken:string}){
 const [inventory,setInventory]=useState<Inventory[]>([])
 const [chosen,setChosen]=useState('')
 const [editVersion,setEditVersion]=useState<number|null>(null)
 const [price,setPrice]=useState('')
 const [cost,setCost]=useState('')
 const [stock,setStock]=useState('')
 const [actor,setActor]=useState('')
 const [reason,setReason]=useState('')
 const [confirmation,setConfirmation]=useState('')
 const [error,setError]=useState('')
 const [notice,setNotice]=useState('')
 const [busy,setBusy]=useState(false)
 const [audit,setAudit]=useState<Event[]>([])
 const selected=inventory.find(r=>r.product_id===chosen)
 async function refresh(){setInventory(await request<Inventory[]>('/api/inventory'))}
 useEffect(()=>{refresh().catch(e=>setError(e.message))},[refreshToken])
 function choose(id:string){setChosen(id);const r=inventory.find(x=>x.product_id===id);setEditVersion(r?.version??null);setPrice(r?.price??'');setCost(r?.cost??'');setStock(String(r?.on_hand??''))}
 async function act(action:()=>Promise<void>){setBusy(true);setError('');setNotice('');try{await action()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function edit(){if(!selected)return;await act(async()=>{
  const updated=await request<Inventory>('/api/demo/inventory/'+chosen,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version:editVersion,actor,reason,price,cost,on_hand:Number(stock)})})
  setEditVersion(updated.version)
  await refresh();onChange();setNotice('Inventario demo actualizado. Los borradores anteriores deben regenerarse; no cambió el catálogo fabricante.')
 })}
 async function reset(){await act(async()=>{
  await request('/api/demo/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmation,actor,reason})})
  await refresh();setConfirmation('');setChosen('');onReset();setNotice('Portfolio demo reiniciado. Estudios históricos no modificados; el evento de reinicio queda auditado.')
 })}
 return <section className="panel"><h2>Catálogo y operación · fuentes separadas</h2><p>8 referencias reales GONHER · Nissan Versa 2012–2025 L4-1.6L · solo declaración del catálogo, no garantía de instalación. GP de aceite; GPS fuera de alcance.</p><div className="catalog-grid">{catalog.map(p=><article className="catalog-card" key={p.id}><strong>{p.reference}</strong><p>{p.description}</p><small>Versa {p.applications[0].year}–{p.applications.at(-1)?.year}</small><a href={p.source.url} target="_blank" rel="noreferrer">Fuente GONHER 2026 · pág. 69</a></article>)}</div>
  <h3>Tabla operacional DEMO · MXN</h3><p>Valores sintéticos creados para probar el flujo. No son precios, costos ni existencias del fabricante.</p><div className="table-scroll"><table aria-label="Inventario DEMO"><thead><tr><th>Referencia</th><th>Precio DEMO</th><th>Costo DEMO</th><th>Existencias</th><th>Reservadas</th><th>Disponibles</th><th>Versión</th></tr></thead><tbody>{inventory.map(r=><tr key={r.product_id}><td>{catalog.find(p=>p.id===r.product_id)?.reference??r.product_id}</td><td>{r.price}</td><td>{r.cost}</td><td>{r.on_hand}</td><td>{r.reserved}</td><td>{r.available}</td><td>{r.version}</td></tr>)}</tbody></table></div><button disabled={busy} onClick={()=>act(refresh)}>Recargar tabla operacional</button>
  <details className="operator"><summary>Operador DEMO · inventario y reinicio</summary><p>Sin credenciales ni identidad verificada: dominio local de aprobación, no autenticación de producción. Úselo para reproducir precio cambiado, margen insuficiente y falta de stock.</p>
   {error&&<p role="alert" className="error">{error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}
   <fieldset disabled={busy}><div className="row"><label>Actor operador<input value={actor} maxLength={100} onChange={e=>setActor(e.target.value)}/></label><label>Motivo operativo<input value={reason} maxLength={1000} onChange={e=>setReason(e.target.value)}/></label></div><label>Artículo operativo<select value={chosen} onChange={e=>choose(e.target.value)}><option value="">Elegir referencia</option>{inventory.map(r=><option key={r.product_id} value={r.product_id}>{catalog.find(p=>p.id===r.product_id)?.reference??r.product_id}</option>)}</select></label><div className="row"><label>Precio DEMO MXN<input value={price} inputMode="decimal" onChange={e=>setPrice(e.target.value)}/></label><label>Costo DEMO MXN<input value={cost} inputMode="decimal" onChange={e=>setCost(e.target.value)}/></label><label>Existencias DEMO<input type="number" min="0" max="1000000" value={stock} onChange={e=>setStock(e.target.value)}/></label></div><button disabled={!selected||actor.trim().length<3||reason.trim().length<5} onClick={edit}>Guardar inventario DEMO</button>{selected&&<><small>Editor basado en v{editVersion}. Una recarga de tabla no sustituye esta versión ni sus campos.</small><button onClick={()=>choose(chosen)}>Recargar artículo en editor (descartar cambios)</button></>}
   <hr/><p>Reinicio destructivo SOLO de solicitudes/reservas en la base portfolio-v1. No borra estudios ni presupuestos de modelos. Auditoría operacional conservada.</p><label>Confirmación de reinicio<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder="RESET PORTFOLIO DEMO"/></label><button className="danger" disabled={confirmation!=='RESET PORTFOLIO DEMO'||actor.trim().length<3||reason.trim().length<5} onClick={reset}>Reiniciar solo portfolio DEMO</button></fieldset>
   <button disabled={busy} onClick={()=>act(async()=>setAudit(await request<Event[]>('/api/inventory/audit')))}>Consultar auditoría operacional</button>{audit.map((e,i)=><article key={i}><strong>{e.action}</strong><p>{e.actor} · {e.reason}</p><details><summary>Antes y después</summary><pre>{JSON.stringify({before:e.before,after:e.after},null,2)}</pre></details></article>)}
  </details>
 </section>
}
