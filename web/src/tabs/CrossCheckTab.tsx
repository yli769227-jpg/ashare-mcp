import { useState } from 'react'
import { ApiError, getCrossCheck } from '../api'
import type { CrossCheckResponse } from '../types'
import { Card } from '../components/Card'
import { Field, PrimaryButton, TextInput } from '../components/Form'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../components/States'
import { fmtNumber } from '../components/format'

export function CrossCheckTab() {
  const [stockCode, setStockCode] = useState('600519')
  const [year, setYear] = useState<number>(2024)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<CrossCheckResponse | null>(null)

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
      const res = await getCrossCheck(stockCode.trim(), Number(year))
      console.info('[CrossCheckTab] ✓ 加载成功', res)
      setData(res)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e)
      console.error('[CrossCheckTab] ✗ 失败', msg)
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
            校验
          </PrimaryButton>
        </form>
      </Card>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} />}
      {!loading && !error && !data && (
        <EmptyState>输入参数后点击「校验」查看勾稽结果</EmptyState>
      )}

      {data && (
        <>
          <Card>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <SummaryStat label="总计" value={data.summary.total} />
              <SummaryStat
                label="通过"
                value={data.summary.passed}
                tone="emerald"
              />
              <SummaryStat
                label="未通过"
                value={data.summary.failed}
                tone="rose"
              />
              <SummaryStat
                label="跳过"
                value={data.summary.skipped}
                tone="slate"
              />
            </div>
          </Card>

          {data.checks.length === 0 ? (
            <EmptyState>暂无勾稽校验项</EmptyState>
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {data.checks.map((c, i) => (
                <article
                  key={`${c.name}-${i}`}
                  className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
                >
                  <header className="flex items-start justify-between gap-3">
                    <div>
                      <h4 className="font-semibold text-slate-800">
                        {c.label || c.name}
                      </h4>
                      <p className="mt-0.5 font-mono text-xs text-slate-400">
                        {c.name}
                      </p>
                    </div>
                    <StatusBadge status={c.status} />
                  </header>
                  {c.formula && (
                    <p className="mt-3 break-all rounded bg-slate-50 px-3 py-2 font-mono text-xs text-slate-700">
                      {c.formula}
                    </p>
                  )}
                  <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                    <DT k="左值" v={fmtNumber(c.lhs_value)} />
                    <DT k="右值" v={fmtNumber(c.rhs_value)} />
                    <DT k="差值" v={fmtNumber(c.diff)} />
                    <DT k="容差" v={fmtNumber(c.tolerance)} />
                  </dl>
                  {c.reason && (
                    <p className="mt-3 text-xs text-slate-500">{c.reason}</p>
                  )}
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function SummaryStat({
  label,
  value,
  tone = 'slate',
}: {
  label: string
  value: number
  tone?: 'slate' | 'emerald' | 'rose'
}) {
  const toneCls = {
    slate: 'text-slate-700',
    emerald: 'text-emerald-700',
    rose: 'text-rose-700',
  }[tone]
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${toneCls}`}>
        {value}
      </p>
    </div>
  )
}

function DT({ k, v }: { k: string; v: string }) {
  return (
    <>
      <dt className="text-slate-500">{k}</dt>
      <dd className="text-right font-mono tabular-nums text-slate-800">{v}</dd>
    </>
  )
}
