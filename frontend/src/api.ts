export async function request<T>(url: string, options?: RequestInit): Promise<T> {
  let response: Response
  try { response = options ? await fetch(url, options) : await fetch(url) }
  catch { throw new Error('No se pudo conectar con el servidor local.') }
  const data = await response.json()
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'Datos no válidos. Revise los campos requeridos y los límites de entrada.'
    throw new Error(detail)
  }
  return data as T
}
