import { test,expect,vi,afterEach } from 'vitest'
import { request } from './portfolio-api'
afterEach(()=>vi.unstubAllGlobals())
test('non-JSON errors become actionable local UI errors rather than parse traces',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,json:async()=>{throw new SyntaxError('private raw body')}}))
 await expect(request('/api/requests')).rejects.toThrow('Respuesta inválida del servidor local')
})
test('validation arrays and transport failures are safe readable errors',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,json:async()=>({detail:[{msg:'private extra data'}]})}))
 await expect(request('/api/requests')).rejects.toThrow('Datos no válidos')
 vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('private network trace')))
 await expect(request('/api/requests')).rejects.toThrow('No se pudo conectar')
})
