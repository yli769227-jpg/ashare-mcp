import type { CheckStatus } from '../types'

const STYLE: Record<CheckStatus, { cls: string; text: string }> = {
  passed: { cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200', text: '通过' },
  failed: { cls: 'bg-rose-50 text-rose-700 ring-rose-200', text: '未通过' },
  skipped: { cls: 'bg-slate-100 text-slate-600 ring-slate-200', text: '跳过' },
}

export function StatusBadge({ status }: { status: CheckStatus }) {
  const s = STYLE[status] ?? STYLE.skipped
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${s.cls}`}
    >
      {s.text}
    </span>
  )
}
