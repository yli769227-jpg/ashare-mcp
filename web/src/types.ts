// 后端 API 返回类型

export interface HealthzResponse {
  status: string
  version: string
}

// ===== Tab 1: 三大报表 =====
export type StatementSection = Record<string, number | string | null>

export interface StatementsResponse {
  stock_code?: string
  company_name?: string
  report_date?: string
  balance_sheet?: StatementSection
  income_statement?: StatementSection
  cash_flow_statement?: StatementSection
  // 兼容后端可能塞的其他字段
  [k: string]: unknown
}

// ===== Tab 2: 勾稽校验 =====
export type CheckStatus = 'passed' | 'failed' | 'skipped'

export interface CheckItem {
  name: string
  label?: string
  formula?: string
  lhs_value?: number | null
  rhs_value?: number | null
  diff?: number | null
  tolerance?: number | null
  status: CheckStatus
  reason?: string
}

export interface CrossCheckSummary {
  total: number
  passed: number
  failed: number
  skipped: number
}

export interface CrossCheckResponse {
  stock_code?: string
  company_name?: string
  report_date?: string
  checks: CheckItem[]
  summary: CrossCheckSummary
}

// ===== Tab 3: 同业对比 =====
export interface ComparePeersRequest {
  stock_codes: string[]
  year: number
  metrics?: string[]
}

export interface CompanyResult {
  stock_code: string
  company_name?: string
  values: Record<string, number | null>
  ranks?: Record<string, number | null>
  fallbacks?: Record<string, string | null>
}

export interface PeersSummary {
  // 每个 metric 对应一个统计对象
  [metric: string]: {
    max?: number | null
    min?: number | null
    avg?: number | null
    std?: number | null
  }
}

export interface PeersError {
  stock_code: string
  error: string
  code?: string
}

export interface ComparePeersResponse {
  year: number
  report_date?: string
  metrics: string[]
  companies: CompanyResult[]
  summary: PeersSummary
  errors: PeersError[]
}

// ===== Tab 4: 历史趋势 =====
export interface HistoryResponse {
  stock_code: string
  company_name?: string
  industry?: string
  years: number[]
  report_dates?: Record<string, string>
  missing_years?: number[]
  series: Record<string, Record<string, number | null>>
  fallbacks?: Record<string, Record<string, string | null>>
  yoy?: Record<string, Record<string, number | null>>
  cagr?: Record<string, number | null>
  stats?: Record<
    string,
    {
      max?: number | null
      min?: number | null
      avg?: number | null
      std?: number | null
    }
  >
  anomalies?: Array<{
    metric: string
    year: number | string
    reason: string
    value?: number | null
  }>
}

// ===== 错误体 =====
export interface ApiErrorBody {
  error: string
  code?: 'INVALID_INPUT' | 'UPSTREAM_ERROR' | string
}
