import type { ReactNode } from 'react'

export function LoadingState({ text = '加载中…' }: { text?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 rounded-lg border border-dashed border-slate-200 bg-white px-6 py-12 text-slate-500">
      <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
      <span>{text}</span>
    </div>
  )
}

export function ErrorState({
  title = '请求失败',
  message,
}: {
  title?: string
  message: string
}) {
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50/60 px-5 py-4">
      <p className="text-sm font-semibold text-rose-800">{title}</p>
      <p className="mt-1 break-all text-sm text-rose-700">{message}</p>
      <p className="mt-2 text-xs text-rose-500">
        提示:请确认后端 (FastAPI :8000) 已启动,或检查参数是否正确。
      </p>
    </div>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 bg-white px-6 py-12 text-center text-sm text-slate-400">
      {children}
    </div>
  )
}
