const configuredBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim()

export const API_BASE = (configuredBase || 'http://127.0.0.1:8000').replace(/\/+$/, '')

export function apiUrl(path: string): string {
  return `${API_BASE}/${path.replace(/^\/+/, '')}`
}

function detailMessage(detail: unknown): string | undefined {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) return '请求参数不完整，请检查输入后重试。'
  return undefined
}

export async function apiRequest<T>(pathOrUrl: string, init?: RequestInit): Promise<T> {
  const url = /^https?:\/\//i.test(pathOrUrl) ? pathOrUrl : apiUrl(pathOrUrl)
  let response: Response
  try {
    response = await fetch(url, init)
  } catch {
    throw new Error('无法连接实验服务。请确认后端已启动，然后重试。')
  }

  const text = await response.text()
  let data: unknown = null
  if (text) {
    try { data = JSON.parse(text) } catch { data = null }
  }
  if (!response.ok) {
    const detail = data && typeof data === 'object' ? detailMessage((data as { detail?: unknown }).detail) : undefined
    throw new Error(detail || `实验服务暂不可用（HTTP ${response.status}）。请稍后重试。`)
  }
  return data as T
}
