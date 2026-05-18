import { useState } from 'react'
import { ApiError, getStatements } from '../api'
import type { StatementsResponse } from '../types'
import { Card } from '../components/Card'
import { Field, PrimaryButton, TextInput } from '../components/Form'
import { KVTable } from '../components/KVTable'
import { EmptyState, ErrorState, LoadingState } from '../components/States'

export function StatementsTab() {
  const [stockCode, setStockCode] = useState('600519')
  const [year, setYear] = useState<number>(2024)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<StatementsResponse | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!stockCode.trim()) {
      setError('请输入股票代码')
      return
    }
    setLoading(true)
    setError(null)
    setData(null)
    try {
      const res = await getStatements(stockCode.trim(), Number(year))
      console.info('[StatementsTab] ✓ 加载成功', res)
      setData(res)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e)
      console.error('[StatementsTab] ✗ 失败', msg)
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card title="查询参数">
        <form
          onSubmit={onSubmit}
          className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_180px_auto] sm:items-end"
        >
          <Field label="股票代码" hint="例如:600519 / 000001">
            <TextInput
              value={stockCode}
              onChange={(e) => setStockCode(e.target.value)}
              placeholder="600519"
            />
          </Field>
          <Field label="年份">
            <TextInput
              type="number"
              value={year}
              min={2000}
              max={2099}
              onChange={(e) => setYear(Number(e.target.value))}
            />
          </Field>
          <PrimaryButton type="submit" loading={loading}>
            拉取
          </PrimaryButton>
        </form>
      </Card>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} />}
      {!loading && !error && !data && (
        <EmptyState>填写参数后点击「拉取」查看三大报表</EmptyState>
      )}

      {data && (
        <>
          <Card>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <h2 className="text-xl font-semibold text-slate-800">
                  {data.company_name || '—'}
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  股票代码 {data.stock_code || stockCode}
                </p>
              </div>
              <div className="text-sm text-slate-500">
                报告期:
                <span className="ml-1 font-mono text-slate-700">
                  {data.report_date || '—'}
                </span>
              </div>
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card title="资产负债表">
              <KVTable data={data.balance_sheet} />
            </Card>
            <Card title="利润表">
              <KVTable data={data.income_statement} />
            </Card>
            <Card title="现金流量表">
              <KVTable data={data.cash_flow_statement} />
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
