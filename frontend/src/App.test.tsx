import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { test, expect, vi, afterEach } from 'vitest'
import App from './App'
import fixture from './api-fixtures.json'
afterEach(() => vi.unstubAllGlobals())
test('seller forms submit structured references and original wording without LLM interpretation', async () => {
 const fetchMock = vi.fn().mockImplementation(async (_url,options)=>({ok:true,json:async()=>options?.method==='POST'?fixture:[]}))
 vi.stubGlobal('fetch',fetchMock)
 const user=userEvent.setup(); render(<App />)
 expect(screen.getByLabelText('Cliente ficticio')).toHaveValue('Taller Rivera (ficticio)')
 expect(screen.getByLabelText('Referencia 1')).toHaveValue('GP-149')
 expect(screen.getByLabelText('Cantidad 1')).toHaveValue('2')
 expect(screen.getByText(/No interpreta lenguaje natural/)).toBeInTheDocument()
 await user.click(screen.getByRole('button',{name:'Identificar y guardar'}))
 const post=fetchMock.mock.calls.find(c=>c[1]?.method==='POST')
 expect(JSON.parse(post![1].body.get('structured_lines'))[0]).toEqual({mode:'pieza',referencia:'GP-149',cantidad:'2'})
 expect(post![1].body.get('email_text')).toBe('Necesito dos filtros GP-149.')
})

test('five realistic samples use varied fictional clients and editable vehicle fields; mixed lines are supported', async () => {
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>[]}))
 const user=userEvent.setup(); render(<App />)
 await user.click(screen.getByRole('button',{name:'Kit Versa 2018'}))
 expect(screen.getByLabelText('Cliente ficticio')).toHaveValue('Servicio Automotriz Los Pinos (ficticio)')
 expect(screen.getByLabelText('Año 1')).toHaveValue('2018')
 expect(screen.getAllByRole('group',{name:/Artículo/})).toHaveLength(3)
 await user.click(screen.getByRole('button',{name:'Agregar referencia'}))
 expect(screen.getByLabelText('Referencia 4')).toHaveValue('')
 await user.click(screen.getByRole('button',{name:'Versa 2021 aceite'}))
 expect(screen.getByLabelText('Cliente ficticio')).toHaveValue('Refaccionaria Ruta Norte (ficticio)')
 await user.click(screen.getByRole('button',{name:'Falta año'}))
 expect(screen.getByLabelText('Año 1')).toHaveValue('')
 expect(screen.getByLabelText('Cliente ficticio')).toHaveValue('Mecánica Integral El Roble (ficticio)')
 await user.click(screen.getByRole('button',{name:'Referencia no cubierta'}))
 expect(screen.getByLabelText('Cliente ficticio')).toHaveValue('Autotaller La Estación (ficticio)')
 expect(screen.getByLabelText('Referencia 1')).toHaveValue('NO-CUBIERTA')
})

test('candidate source edition and page are visible; fictional transaction is separate from real catalog', async () => {
 vi.stubGlobal('fetch',vi.fn().mockImplementation(async (_url,options)=>({ok:true,json:async()=>options?.method==='POST'?fixture:[]})))
 const user=userEvent.setup(); render(<App />)
 await user.click(screen.getByRole('button',{name:'Identificar y guardar'}))
 const result=await screen.findByRole('region',{name:'Resultado de identificación'})
 expect(within(result).getByRole('link',{name:'GONHER 2026 · página impresa 69'})).toHaveAttribute('href',fixture.lines[0].candidates[0].source.url)
 expect(within(result).getByText(/Transacción ficticia/)).toBeInTheDocument()
 expect(within(result).queryByText('Sintético')).not.toBeInTheDocument()
 expect(within(result).getByText(/Referencia exacta no demuestra compatibilidad vehicular/)).toBeInTheDocument()
})

test.each([409,422,500])('HTTP %s cannot show a false saved result', async status => {
 vi.stubGlobal('fetch',vi.fn().mockImplementation(async (_url,options)=>options?.method ? {ok:false,status,json:async()=>({detail:'No guardado'})} : {ok:true,json:async()=>[]}))
 const user=userEvent.setup(); render(<App />)
 await user.click(screen.getByRole('button',{name:'Identificar y guardar'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('No guardado')
 expect(screen.queryByRole('region',{name:'Resultado de identificación'})).not.toBeInTheDocument()
})
test('history detail copies structured fields under a new ID without altering original record', async () => {
 vi.stubGlobal('fetch',vi.fn().mockImplementation(async url=>({ok:true,json:async()=>url==='/api/cases'?[fixture]:url.startsWith('/api/cases/')?fixture:[]})))
 const user=userEvent.setup(); render(<App />)
 await user.click(await screen.findByRole('button',{name:'Ver solicitud fixture'}))
 await screen.findByRole('region',{name:'Resultado de identificación'})
 const old=(screen.getByLabelText('Identificador de solicitud') as HTMLInputElement).value
 await user.click(screen.getByRole('button',{name:'Copiar para aclarar'}))
 expect(screen.getByLabelText('Mensaje original editable')).toHaveValue(fixture.email_text)
 expect(screen.getByLabelText('Referencia 1')).toHaveValue('GP-149')
 expect((screen.getByLabelText('Identificador de solicitud') as HTMLInputElement).value).not.toBe(old)
})
test('editing and resubmission are disabled during save', async () => {
 let finish!: (value:unknown)=>void
 const fetchMock=vi.fn().mockImplementation(async (_url,options)=>options?.method?new Promise(resolve=>{finish=resolve}):{ok:true,json:async()=>[]})
 vi.stubGlobal('fetch',fetchMock)
 const user=userEvent.setup(); render(<App />)
 await user.click(screen.getByRole('button',{name:'Identificar y guardar'}))
 expect(screen.getByLabelText('Referencia 1')).toBeDisabled()
 expect(screen.getByRole('button',{name:'Guardando…'})).toBeDisabled()
 expect(screen.getByRole('button',{name:'Nueva solicitud'})).toBeDisabled()
 finish({ok:true,json:async()=>fixture})
 await screen.findByRole('region',{name:'Resultado de identificación'})
})
