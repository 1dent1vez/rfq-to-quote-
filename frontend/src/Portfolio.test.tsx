import { render, screen, waitFor } from '@testing-library/react'

function setup(current: typeof fixture.pending | typeof fixture.draft=fixture.pending){
 const fetchMock=vi.fn().mockImplementation(async(url,options)=>{
  if(!options?.method)return {ok:true,json:async()=>url==='/api/catalog'?fixture.catalog:url==='/api/inventory'?fixture.inventory:url==='/api/requests'?[current]:current}
  const next=url.endsWith('/review')?fixture.reviewed:url.endsWith('/draft')?fixture.draft:url.endsWith('/approve')?fixture.approved:fixture.pending
  return {ok:true,json:async()=>next}
 })
 vi.stubGlobal('fetch',fetchMock);render(<Portfolio />);return fetchMock
}

async function open(user:ReturnType<typeof userEvent.setup>){await user.click(await screen.findByRole('button',{name:/Taller ficticio/}))}

test('human revisions add supplemental evidence with actor reason and optimistic version',async()=>{
 const mock=setup();const user=userEvent.setup()
 expect(await screen.findByRole('button',{name:/Taller ficticio/})).toHaveTextContent('Pendiente de revisión')
 await open(user)
 await user.selectOptions(screen.getByLabelText('Referencia revisada 1'),'gonher-gp-149')
 await user.clear(screen.getByLabelText('Cantidad revisada 1'));await user.type(screen.getByLabelText('Cantidad revisada 1'),'3')
 await user.type(screen.getByLabelText('Evidencia suplementaria nueva'),'Cliente confirma tres piezas por referencia y entrega local.')
 await user.type(screen.getByLabelText('Actor demo'),'Vendedor')
 await user.type(screen.getByLabelText('Motivo de revisión / aprobación'),'Confirmación telefónica ficticia')
 await user.selectOptions(screen.getByLabelText('Clasificación fragmento 1'),'resolved_context')
 await user.type(screen.getByLabelText('Motivo fragmento 1'),'Se confirmó entrega local sin plazo prometido')
 await user.click(screen.getByRole('button',{name:'Guardar revisión y evidencia'}))
 await waitFor(()=>expect(screen.getByRole('button',{name:'Crear borrador'})).toBeEnabled())
 const call=mock.mock.calls.find(c=>c[0].endsWith('/review'))
 const body=JSON.parse(call![1].body)
 expect(body.version).toBe(1);expect(body.lines[0].quantity).toBe(3);expect(body.actor).toBe('Vendedor')
 expect(body.supplement).toContain('Cliente confirma');expect(body.fragments[0].kind).toBe('resolved_context')
 expect(body.original).toBeUndefined()
})

test('draft approval binds exact snapshot and version; approved downloads and audit visible',async()=>{
 const mock=setup(fixture.draft);const user=userEvent.setup();await open(user)
 await user.type(screen.getByLabelText('Actor demo'),'Supervisor')
 await user.type(screen.getByLabelText('Motivo de revisión / aprobación'),'Acepto reglas demo explícitas')
 expect(screen.getByRole('button',{name:'Aprobar y reservar DEMO'})).toBeDisabled()
 const readsBefore=mock.mock.calls.filter(c=>c[0]==='/api/inventory').length
 await user.click(screen.getByLabelText(/Acepto la versión/))
 await user.click(screen.getByRole('button',{name:'Aprobar y reservar DEMO'}))
 const link=await screen.findByRole('link',{name:'Descargar HTML imprimible'})
 await waitFor(()=>expect(mock.mock.calls.filter(c=>c[0]==='/api/inventory').length).toBeGreaterThan(readsBefore))
 expect(link).toHaveAttribute('href',`/api/requests/${fixture.approved.id}/download.html`)
 expect(await screen.findByRole('link',{name:'Descargar CSV'})).toHaveAttribute('download')
 expect(screen.getByLabelText('Referencia revisada 1')).toBeDisabled()
 const body=JSON.parse(mock.mock.calls.find(c=>c[0].endsWith('/approve'))![1].body)
 expect(body.version).toBe(fixture.draft.version);expect(body.snapshot).toBe(fixture.draft.quote.snapshot)
 expect(screen.getByText('quote_approved')).toBeInTheDocument()
})

test('stale approval error never shows download; reload is explicit',async()=>{
 const mock=setup(fixture.draft)
 mock.mockImplementation(async(url,options)=>options?.method?{ok:false,json:async()=>({detail:'Cambió inventario; regenere borrador'})}:{ok:true,json:async()=>url==='/api/catalog'?fixture.catalog:url==='/api/inventory'?fixture.inventory:url==='/api/requests'?[fixture.draft]:fixture.draft})
 const user=userEvent.setup();await open(user)
 await user.type(screen.getByLabelText('Actor demo'),'Supervisor');await user.type(screen.getByLabelText('Motivo de revisión / aprobación'),'Acepto revisión demo')
 await user.click(screen.getByLabelText(/Acepto la versión/));await user.click(screen.getByRole('button',{name:'Aprobar y reservar DEMO'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('Cambió inventario')
 expect(screen.queryByRole('link',{name:'Descargar CSV'})).not.toBeInTheDocument()
 expect(screen.getByRole('button',{name:'Recargar versión guardada'})).toBeEnabled()
})
import userEvent from '@testing-library/user-event'
import { test, expect, vi, afterEach } from 'vitest'
import Portfolio from './Portfolio'
import fixture from './portfolio-fixtures.json'
test('unsaved review disables draft and exact approval until new revision saved',async()=>{
 setup(fixture.draft);const user=userEvent.setup();await open(user)
 await user.type(screen.getByLabelText('Actor demo'),'Supervisor');await user.type(screen.getByLabelText('Motivo de revisión / aprobación'),'Acepto versión sintética')
 await user.click(screen.getByLabelText(/Acepto la versión/))
 await user.clear(screen.getByLabelText('Cantidad revisada 1'));await user.type(screen.getByLabelText('Cantidad revisada 1'),'4')
 expect(screen.getByRole('button',{name:'Crear borrador'})).toBeDisabled()
 expect(screen.getByRole('button',{name:'Aprobar y reservar DEMO'})).toBeDisabled()
 expect(screen.getByLabelText(/Acepto la versión/)).not.toBeChecked()
})

test('operator edits synthetic inventory with reason/version and guarded reset',async()=>{
 const mock=setup();const user=userEvent.setup()
 await user.click(screen.getByText('Operador DEMO · inventario y reinicio'))
 await user.selectOptions(screen.getByLabelText('Artículo operativo'),'gonher-gp-149')
 await user.clear(screen.getByLabelText('Precio DEMO MXN'));await user.type(screen.getByLabelText('Precio DEMO MXN'),'160.00')
 await user.type(screen.getByLabelText('Actor operador'),'Operador')
 await user.type(screen.getByLabelText('Motivo operativo'),'Reproducir borrador obsoleto')
 await user.click(screen.getByRole('button',{name:'Guardar inventario DEMO'}))
 const call=mock.mock.calls.find(c=>c[0]==='/api/demo/inventory/gonher-gp-149')
 expect(JSON.parse(call![1].body)).toMatchObject({price:'160.00',actor:'Operador',reason:'Reproducir borrador obsoleto',version:fixture.inventory.find(r=>r.product_id==='gonher-gp-149')!.version})
 expect(screen.getByRole('button',{name:'Reiniciar solo portfolio DEMO'})).toBeDisabled()
 await user.type(screen.getByLabelText('Confirmación de reinicio'),'RESET PORTFOLIO DEMO')
 expect(screen.getByRole('button',{name:'Reiniciar solo portfolio DEMO'})).toBeEnabled()
})

test('attachment rejects oversized file before sending to server',async()=>{
 const mock=setup();const user=userEvent.setup()
 await user.upload(screen.getByLabelText('Adjunto TXT/CSV'),new File(['a'.repeat(20001)],'demo.txt',{type:'text/plain'}))
 await user.click(screen.getByRole('button',{name:'Recibir solicitud'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('20000 bytes')
 expect(mock.mock.calls.some(c=>c[1]?.method==='POST')).toBe(false)
})

test('inventory editor keeps its displayed version after unrelated table refresh',async()=>{
 const mock=setup();const user=userEvent.setup()
 await user.click(screen.getByText('Operador DEMO · inventario y reinicio'))
 await user.selectOptions(screen.getByLabelText('Artículo operativo'),'gonher-gp-149')
 const original=fixture.inventory.find(r=>r.product_id==='gonher-gp-149')!
 mock.mockImplementation(async(url,options)=>({ok:true,json:async()=>url==='/api/inventory'?fixture.inventory.map(r=>({...r,version:r.version+1,price:'190.00'})):options?.method?fixture.pending:[]}))
 await user.click(screen.getByRole('button',{name:'Recargar tabla operacional'}))
 await user.type(screen.getByLabelText('Actor operador'),'Operador');await user.type(screen.getByLabelText('Motivo operativo'),'Edición basada en versión visible')
 await user.click(screen.getByRole('button',{name:'Guardar inventario DEMO'}))
 const call=mock.mock.calls.find(c=>c[0]==='/api/demo/inventory/gonher-gp-149')
 expect(JSON.parse(call![1].body).version).toBe(original.version)
})

afterEach(()=>vi.unstubAllGlobals())
test('offline intake defaults manual; explicit suggestions preserve original in review',async()=>{
 const fetchMock=vi.fn().mockImplementation(async(url,options)=>({ok:true,json:async()=>url==='/api/catalog'?fixture.catalog:url==='/api/inventory'?fixture.inventory:options?.method?fixture.pending:[]}))
 vi.stubGlobal('fetch',fetchMock)
 const user=userEvent.setup();render(<Portfolio />)
 expect(screen.getByLabelText('Sugerencias offline (no LLM)')).not.toBeChecked()
 await user.click(screen.getByLabelText('Sugerencias offline (no LLM)'))
 await user.click(screen.getByRole('button',{name:'Recibir solicitud'}))
 expect(await screen.findByText('2 GP-149; entrega urgente',{selector:'pre'})).toBeInTheDocument()
 expect(screen.getByRole('heading',{name:'2. Revisión humana'})).toBeInTheDocument()
 const call=fetchMock.mock.calls.find(c=>c[1]?.method==='POST')
 expect(JSON.parse(call![1].body).suggestions).toBe(true)
 expect(screen.getByText('Línea pendiente de revisión')).toBeInTheDocument()
 expect(screen.getByLabelText('Referencia revisada 1')).toHaveValue('')
})
