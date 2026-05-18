// 数字格式化:千分位、null → "—"、保留有效位

const EMPTY = '—'

export function fmtNumber(
  v: number | string | null | undefined,
  opts?: { digits?: number; percent?: boolean },
): string {
  if (v === null || v === undefined || v === '') return EMPTY
  const n = typeof v === 'string' ? Number(v) : v
  if (typeof n !== 'number' || !Number.isFinite(n)) return EMPTY

  if (opts?.percent) {
    return `${(n * 100).toLocaleString('zh-CN', {
      maximumFractionDigits: opts.digits ?? 2,
      minimumFractionDigits: opts.digits ?? 2,
    })}%`
  }

  const digits = opts?.digits
  if (digits !== undefined) {
    return n.toLocaleString('zh-CN', {
      maximumFractionDigits: digits,
      minimumFractionDigits: digits,
    })
  }
  // 财报数字通常是亿级整数,保留 2 位小数兜底
  if (Number.isInteger(n)) {
    return n.toLocaleString('zh-CN')
  }
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

export function fmtAny(v: unknown): string {
  if (v === null || v === undefined || v === '') return EMPTY
  if (typeof v === 'number') return fmtNumber(v)
  return String(v)
}
