import { useState } from 'react'
import { ApiError, postComparePeers } from '../api'
import type { ComparePeersResponse } from '../types'
import { Card } from '../components/Card'
import {
  Field,
  PrimaryButton,
  TextArea,
  TextInput,
} from '../components/Form'
import { EmptyState, ErrorState, LoadingState } from '../components/States'
import { fmtNumber } from '../components/format'

function parseList(s: string): string[] {
  return s
    .split(/[\s,，;；\n]+/)
    .map((x) => x.trim())
    .filter(Boolean)
}

export function ComparePeersTab() {
  const [codesRaw, setCodesRaw] = useState('600519\n000858\n000596')
  const [year, setYear] = useState<number>(2024)
  const [metricsRaw, setMetricsRaw] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<ComparePeersResponse | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    const codes = parseList(codesRaw)
    if (codes.length < 2) {
      setError('请至少输入 2 个股票代码')
      return
    }
    const metrics = parseList(metricsRaw)
    setLoading(true)
    setError(null)
    setData(null)
    try {
      const res = await postComparePeers({
        stock_codes: codes,
        year: Number(year),
        ...(metrics.length ? { metrics } : {}),
      })
      console.info('[ComparePeersTab] ✓ 加载成功', res)
      setData(res)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e)
      console.error('[ComparePeersTab] ✗ 失败', msg)
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card title="查询参数">
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Field
              label="股票代码"
              hint="支持逗号 / 换行 / 分号分隔,至少 2 个"
            >
              <TextArea
                rows={4}
                value={codesRaw}
                onChange={(e) => setCodesRaw(e.target.value)}
                placeholder="600519, 000858, 000596"
              />
            </Field>
            <div className="space-y-4">
              <Field label="年份">
                <TextInput
                  type="number"
                  value={year}
                  min={2000}
                  max={2099}
                  onChange={(e) => setYear(Number(e.target.value))}
                />
              </Field>
              <Field label="指标(可选)" hint="留空使用后端默认指标集">
                <TextInput
                  value={metricsRaw}
                  onChange={(e) => setMetricsRaw(e.target.value)}
                  placeholder="例如:revenue, net_profit, total_assets"
                />
              </Field>
            </div>
          </div>
          <div className="flex justify-end">
            <PrimaryButton type="submit" loading={loading}>
              对比
            </PrimaryButton>
          </div>
        </form>
      </Card>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} />}
      {!loading && !error && !data && (
        <EmptyState>填写多个代码后点击「对比」</EmptyState>
      )}

      {data && (
        <>
          <Card
            title="同业对比"
            subtitle={`年份 ${data.year} · 报告期 ${data.report_date || '—'}`}
          >
            {data.companies.length === 0 ? (
              <EmptyState>没有可对比的数据</EmptyState>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-max text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50/60 text-left">
                      <th className="px-3 py-2 font-medium text-slate-500">
                        指标
                      </th>
                      {data.companies.map((c) => (
                        <th
                          key={c.stock_code}
                          className="px-3 py-2 font-medium text-slate-700"
                        >
                          <div>{c.company_name || c.stock_code}</div>
                          <div className="font-mono text-xs text-slate-400">
                            {c.stock_code}
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.metrics.map((m, i) => (
                      <tr
                        key={m}
                        className={
                          i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'
                        }
                      >
                        <td className="px-3 py-2 text-slate-600">{m}</td>
                        {data.companies.map((c) => {
                          const v = c.values?.[m]
                          const rank = c.ranks?.[m]
                          const fb = c.fallbacks?.[m]
                          return (
                            <td
                              key={c.stock_code}
                              className="px-3 py-2 text-right font-mono tabular-nums"
                            >
                              <div className="text-slate-800">
                                {fmtNumber(v)}
                              </div>
                              <div className="text-xs text-slate-400">
                                {rank != null ? `排名 ${rank}` : ''}
                                {fb ? ` · ${fb}` : ''}
                              </div>
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {data.summary && Object.keys(data.summary).length > 0 && (
            <Card title="统计摘要">
              <div className="overflow-x-auto">
                <table className="w-full min-w-max text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50/60 text-left">
                      <th className="px-3 py-2 font-medium text-slate-500">
                        指标
                      </th>
                      <th className="px-3 py-2 text-right font-medium text-slate-500">
                        最大
                      </th>
                      <th className="px-3 py-2 text-right font-medium text-slate-500">
                        最小
                      </th>
                      <th className="px-3 py-2 text-right font-medium text-slate-500">
                        均值
                      </th>
                      <th className="px-3 py-2 text-right font-medium text-slate-500">
                        标准差
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.summary).map(([m, s], i) => (
                      <tr
                        key={m}
                        className={
                          i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'
                        }
                      >
                        <td className="px-3 py-2 text-slate-600">{m}</td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-800">
                          {fmtNumber(s?.max)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-800">
                          {fmtNumber(s?.min)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-800">
                          {fmtNumber(s?.avg)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-800">
                          {fmtNumber(s?.std)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {data.errors && data.errors.length > 0 && (
            <Card title="单家失败">
              <ul className="space-y-2">
                {data.errors.map((e, i) => (
                  <li
                    key={`${e.stock_code}-${i}`}
                    className="rounded border border-rose-200 bg-rose-50/60 px-3 py-2 text-sm"
                  >
                    <span className="font-mono font-semibold text-rose-700">
                      {e.stock_code}
                    </span>
                    <span className="ml-2 text-rose-700">{e.error}</span>
                    {e.code && (
                      <span className="ml-2 text-xs text-rose-400">
                        ({e.code})
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
