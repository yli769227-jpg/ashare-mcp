import type { ReactNode } from 'react'

interface CardProps {
  title?: ReactNode
  subtitle?: ReactNode
  children: ReactNode
  className?: string
}

export function Card({ title, subtitle, children, className }: CardProps) {
  return (
    <section
      className={`rounded-lg border border-slate-200 bg-white shadow-sm ${className ?? ''}`}
    >
      {(title || subtitle) && (
        <header className="border-b border-slate-100 px-5 py-3">
          {title && (
            <h3 className="text-base font-semibold text-slate-800">{title}</h3>
          )}
          {subtitle && (
            <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>
          )}
        </header>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  )
}
