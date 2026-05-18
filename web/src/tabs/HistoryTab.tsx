import { useState } from 'react'
import { ApiError, getHistory } from '../api'
import type { HistoryResponse } from '../types'
import { Card } from '../components/Card'
import { Field, PrimaryButton, TextInput } from '../components/Form'
import { EmptyState, ErrorState, LoadingState } from '../components/States'
import { fmtNumber } from '../components/format'

export function HistoryTab() {
  const [stockCode, setStockCode] = useState('600519')
  const [years, setYears] = useState<number>(5)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<HistoryResponse | null>(null)

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
      const res = await getHistory(stockCode.trim(), Number(years))
      console.info('[HistoryTab] ✓ 加载成功', res)
      setData(res)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e)
      console.error('[HistoryTab] ✗ 失败', msg)
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
          <Field label="股票代码">
            <TextInput
              value={stockCode}
              onChange={(e) => setStockCode(e.target.value)}
              placeholder="600519"
            />
          </Field>
          <Field label="年数" hint="向前回溯的年数">
            <TextInput
              type="number"
              value={years}
              min={1}
              max={20}
              onChange={(e) => setYears(Number(e.target.value))}
            />
          </Field>
          <PrimaryButton type="submit" loading={loading}>
            查询
          </PrimaryButton>
        </form>
      </Card>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} />}
      {!loading && !error && !data && (
        <EmptyState>查询后查看多年趋势</EmptyState>
      )}

      {data && <HistoryResult data={data} />}
    </div>
  )
}

function HistoryResult({ data }: { data: HistoryResponse }) {
  const years = data.years ?? []
  const seriesMetrics = Object.keys(data.series || {})
  const yoyMetrics = Object.keys(data.yoy || {})
  const cagrMetrics = Object.keys(data.cagr || {})

  return (
    <div className="space-y-6">
      <Card>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Info label="公司" value={data.company_name || '—'} />
          <Info label="行业" value={data.industry || '—'} />
          <Info
            label="覆盖年份"
            value={years.length ? years.join(', ') : '—'}
          />
        </div>
        {data.missing_years && data.missing_years.length > 0 && (
          <p className="mt-3 text-xs text-amber-700">
            ⚠️ 缺失年份:{data.missing_years.join(', ')}
          </p>
        )}
      </Card>

      <Card title="指标序列" subtitle="行=指标,列=年份">
        {seriesMetrics.length === 0 || years.length === 0 ? (
          <EmptyState>暂无序列数据</EmptyState>
        ) : (
          <YearMatrix
            years={years}
            metrics={seriesMetrics}
            values={data.series}
          />
        )}
      </Card>

      {yoyMetrics.length > 0 && (
        <Card title="同比 YoY" subtitle="百分比变化">
          <YearMatrix
            years={years}
            metrics={yoyMetrics}
            values={data.yoy ?? {}}
            percent
          />
        </Card>
      )}

      {cagrMetrics.length > 0 && (
        <Card title="CAGR(复合年化增长率)">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {cagrMetrics.map((m) => (
              <div
                key={m}
                className="rounded-md border border-slate-100 bg-slate-50/60 px-3 py-2"
              >
                <p className="text-xs text-slate-500">{m}</p>
                <p className="mt-1 font-mono text-base font-semibold tabular-nums text-slate-800">
                  {fmtNumber(data.cagr?.[m], { percent: true })}
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {data.anomalies && data.anomalies.length > 0 && (
        <Card title="异常点" subtitle="后端检测到的可疑数据">
          <ul className="space-y-2">
            {data.anomalies.map((a, i) => (
              <li
                key={`${a.metric}-${i}`}
                className="rounded border border-amber-200 bg-amber-50/60 px-3 py-2 text-sm"
              >
                <span className="font-semibold text-amber-800">
                  {a.metric} · {a.year}
                </span>
                {a.value != null && (
                  <span className="ml-2 font-mono text-amber-700">
                    值={fmtNumber(a.value)}
                  </span>
                )}
                <span className="ml-2 text-amber-700">{a.reason}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}

function YearMatrix({
  years,
  metrics,
  values,
  percent,
}: {
  years: number[]
  metrics: string[]
  values: Record<string, Record<string, number | null>>
  percent?: boolean
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-max text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50/60 text-left">
            <th className="px-3 py-2 font-medium text-slate-500">指标</th>
            {years.map((y) => (
              <th
                key={y}
                className="px-3 py-2 text-right font-medium text-slate-500"
              >
                {y}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map((m, i) => {
            const row = values[m] || {}
            return (
              <tr
                key={m}
                className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'}
              >
                <td className="px-3 py-2 text-slate-600">{m}</td>
                {years.map((y) => {
                  const v = row[String(y)]
                  return (
                    <td
                      key={y}
                      className="px-3 py-2 text-right font-mono tabular-nums text-slate-800"
                    >
                      {fmtNumber(v, percent ? { percent: true } : undefined)}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-base text-slate-800">{value}</p>
    </div>
  )
}
