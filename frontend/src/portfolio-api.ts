export async function request<T>(url:string,options?:RequestInit):Promise<T>{
 let response:Response
 try{response=options?await fetch(url,options):await fetch(url)}catch{throw new Error('No se pudo conectar con el servidor local. Compruebe que run-demo.sh sigue activo.')}
 let data:unknown
 try{data=await response.json()}catch{throw new Error('Respuesta inválida del servidor local. Recargue y compruebe el servicio.')}
 if(!response.ok){
  const detail=data&&typeof data==='object'&&'detail' in data?data.detail:null
  throw new Error(typeof detail==='string'?detail:'Datos no válidos. Revise campos, límites y formatos; no se aplicaron cambios.')
 }
 return data as T
}
