import type {
  ApiErrorBody,
  ComparePeersRequest,
  ComparePeersResponse,
  CrossCheckResponse,
  HealthzResponse,
  HistoryResponse,
  StatementsResponse,
} from './types'

const RAW_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ||
  'http://localhost:8000'
export const API_BASE = RAW_BASE.replace(/\/+$/, '')

export class ApiError extends Error {
  status: number
  code?: string
  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`
  // 关键路径日志:请求开始
  console.info('[api] →', init?.method || 'GET', url)
  let res: Response
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers || {}),
      },
    })
  } catch (e) {
    console.error('[api] ✗ 网络错误', url, e)
    const msg = e instanceof Error ? e.message : String(e)
    throw new ApiError(
      `无法连接到后端 (${API_BASE}): ${msg}`,
      0,
      'NETWORK_ERROR',
    )
  }

  const text = await res.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }

  if (!res.ok) {
    const errBody = body as Partial<ApiErrorBody> | null
    const msg =
      (errBody && typeof errBody.error === 'string' && errBody.error) ||
      `HTTP ${res.status}`
    const code =
      errBody && typeof errBody.code === 'string' ? errBody.code : undefined
    console.error('[api] ✗', res.status, url, msg)
    throw new ApiError(msg, res.status, code)
  }

  console.info('[api] ✓', res.status, url)
  return body as T
}

export function getHealthz(): Promise<HealthzResponse> {
  return request<HealthzResponse>('/healthz')
}

export function getStatements(
  stockCode: string,
  year: number,
): Promise<StatementsResponse> {
  const q = new URLSearchParams({ stock_code: stockCode, year: String(year) })
  return request<StatementsResponse>(`/api/statements?${q.toString()}`)
}

export function getCrossCheck(
  stockCode: string,
  year: number,
): Promise<CrossCheckResponse> {
  const q = new URLSearchParams({ stock_code: stockCode, year: String(year) })
  return request<CrossCheckResponse>(`/api/cross-check?${q.toString()}`)
}

export function postComparePeers(
  payload: ComparePeersRequest,
): Promise<ComparePeersResponse> {
  return request<ComparePeersResponse>('/api/compare-peers', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getHistory(
  stockCode: string,
  years: number,
): Promise<HistoryResponse> {
  const q = new URLSearchParams({
    stock_code: stockCode,
    years: String(years),
  })
  return request<HistoryResponse>(`/api/history?${q.toString()}`)
}
