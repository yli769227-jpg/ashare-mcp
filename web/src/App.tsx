import { useEffect, useState } from 'react'
import { API_BASE, getHealthz } from './api'
import { StatementsTab } from './tabs/StatementsTab'
import { CrossCheckTab } from './tabs/CrossCheckTab'
import { ComparePeersTab } from './tabs/ComparePeersTab'
import { HistoryTab } from './tabs/HistoryTab'

const REPO_URL = 'https://github.com/yli769227-jpg/ashare-mcp'

type TabKey = 'statements' | 'cross-check' | 'compare-peers' | 'history'

interface TabDef {
  key: TabKey
  label: string
  desc: string
}

const TABS: TabDef[] = [
  { key: 'statements', label: '三大报表', desc: '资产负债 / 利润 / 现金流' },
  { key: 'cross-check', label: '勾稽校验', desc: '财报恒等式自动核对' },
  { key: 'compare-peers', label: '同业对比', desc: '多家公司指标横评' },
  { key: 'history', label: '历史趋势', desc: '多年序列 / YoY / CAGR' },
]

type Health = 'unknown' | 'ok' | 'down'

function App() {
  const [active, setActive] = useState<TabKey>('statements')
  const [health, setHealth] = useState<Health>('unknown')
  const [version, setVersion] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    console.info('[App] 后端健康检查', API_BASE)
    getHealthz()
      .then((r) => {
        if (cancelled) return
        setHealth('ok')
        setVersion(r.version || null)
      })
      .catch((e) => {
        if (cancelled) return
        console.warn('[App] 后端不可达', e)
        setHealth('down')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="flex min-h-full flex-col">
      <Header health={health} version={version} />

      <nav className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap gap-1 px-4 sm:px-6">
          {TABS.map((t) => {
            const isActive = active === t.key
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => setActive(t.key)}
                className={`relative -mb-px border-b-2 px-4 py-3 text-sm font-medium transition ${
                  isActive
                    ? 'border-brand-600 text-brand-700'
                    : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
              >
                <span>{t.label}</span>
                <span className="ml-2 text-xs font-normal text-slate-400">
                  {t.desc}
                </span>
              </button>
            )
          })}
        </div>
      </nav>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6">
        {active === 'statements' && <StatementsTab />}
        {active === 'cross-check' && <CrossCheckTab />}
        {active === 'compare-peers' && <ComparePeersTab />}
        {active === 'history' && <HistoryTab />}
      </main>

      <Footer />
    </div>
  )
}

function Header({ health, version }: { health: Health; version: string | null }) {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-5 sm:px-6">
        <div>
          <div className="flex items-baseline gap-3">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
              ashare-mcp
            </h1>
            <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
              A 股财报工具
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            基于 MCP 的 A 股上市公司财报查询、勾稽校验、同业对比与历史趋势分析
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <HealthDot health={health} version={version} />
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-slate-700 transition hover:bg-slate-50"
          >
            <svg
              viewBox="0 0 24 24"
              className="h-4 w-4"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M12 .5C5.73.5.78 5.45.78 11.72c0 4.93 3.2 9.11 7.63 10.59.56.1.77-.24.77-.54v-2.09c-3.11.68-3.77-1.32-3.77-1.32-.51-1.29-1.24-1.63-1.24-1.63-1.01-.69.08-.68.08-.68 1.12.08 1.71 1.15 1.71 1.15 1 1.71 2.62 1.21 3.26.93.1-.72.39-1.21.71-1.49-2.48-.28-5.09-1.24-5.09-5.51 0-1.22.43-2.21 1.14-2.99-.11-.28-.5-1.42.11-2.96 0 0 .94-.3 3.07 1.14.89-.25 1.85-.37 2.81-.38.96.01 1.92.13 2.81.38 2.13-1.44 3.06-1.14 3.06-1.14.62 1.54.23 2.68.12 2.96.71.78 1.13 1.77 1.13 2.99 0 4.28-2.61 5.22-5.1 5.5.4.34.76 1.02.76 2.06v3.05c0 .3.21.65.78.54 4.42-1.48 7.62-5.66 7.62-10.59C23.22 5.45 18.27.5 12 .5z" />
            </svg>
            GitHub
          </a>
        </div>
      </div>
    </header>
  )
}

function HealthDot({
  health,
  version,
}: {
  health: Health
  version: string | null
}) {
  const cfg = {
    unknown: { dot: 'bg-slate-300', text: '后端状态:检测中' },
    ok: {
      dot: 'bg-emerald-500',
      text: `后端在线${version ? ` · v${version}` : ''}`,
    },
    down: { dot: 'bg-rose-500', text: '后端离线' },
  }[health]
  return (
    <span
      className="inline-flex items-center gap-2 rounded-md bg-slate-50 px-2.5 py-1.5 text-xs text-slate-600"
      title={API_BASE}
    >
      <span className={`h-2 w-2 rounded-full ${cfg.dot}`} />
      {cfg.text}
    </span>
  )
}

function Footer() {
  return (
    <footer className="mt-10 border-t border-slate-200 bg-white py-6">
      <div className="mx-auto max-w-6xl px-4 text-center text-xs text-slate-400 sm:px-6">
        <p>
          数据来源:东方财富(akshare)· 仅供学习研究,不构成投资建议。
        </p>
        <p className="mt-1">
          API:
          <code className="ml-1 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-slate-600">
            {API_BASE}
          </code>
        </p>
      </div>
    </footer>
  )
}

export default App
