import { data } from '../data'

/** 0.234 -> "23%", 0.0158 -> "1.6%". One decimal only where it matters. */
export const pct = (x: number): string => {
  const v = x * 100
  return v < 10 ? `${v.toFixed(1)}%` : `${Math.round(v)}%`
}

export const money = (x: number): string => `$${x.toFixed(2)}`

export const repoShort = (repo: string): string => repo.split('/').pop() ?? repo

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const

export const month = (d: string | null): string => {
  if (!d) return 'unknown'
  const [y, m] = d.split('-')
  return `${MONTHS[Number(m) - 1] ?? '?'} ${y}`
}

/** "trpc/trpc" + "trpc__trpc-7477" -> "trpc/trpc #7477" */
export const taskName = (instanceIndex: number): string => {
  const inst = data.instances[instanceIndex]
  if (!inst) return 'unknown task'
  const m = /^.*-(\d+)$/.exec(inst.id)
  return m ? `${inst.repo} #${m[1]}` : inst.id
}

export const taskNumber = (id: string): string => {
  const m = /^.*-(\d+)$/.exec(id)
  return m ? `#${m[1]}` : id
}

export const LANG_LABEL: Record<string, string> = { typescript: 'TypeScript', python: 'Python', java: 'Java' }
