import { fmtAny } from './format'

// 两列字段表:键左、值右
interface KVTableProps {
  data: Record<string, unknown> | null | undefined
  emptyText?: string
}

export function KVTable({ data, emptyText = '暂无数据' }: KVTableProps) {
  const entries = data ? Object.entries(data) : []
  if (entries.length === 0) {
    return <p className="text-sm text-slate-400">{emptyText}</p>
  }
  return (
    <div className="overflow-hidden rounded-md border border-slate-100">
      <table className="w-full text-sm">
        <tbody>
          {entries.map(([k, v], i) => (
            <tr
              key={k}
              className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/60'}
            >
              <td className="w-1/2 break-all px-3 py-2 text-slate-500">{k}</td>
              <td className="break-all px-3 py-2 text-right font-mono tabular-nums text-slate-800">
                {fmtAny(v)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
