import { data } from '../data'
import { repoShort } from './format'

/** Facts computed from the results, so prose on the page can never drift from the numbers. */

const { models, instances, attempts, totals, dataset } = data

const withData = models.filter((m) => m.attempts > 0)
const paidWithData = withData.filter((m) => m.tier === 'paid')
const local = withData.filter((m) => m.tier === 'local')

export const top = paidWithData.reduce((a, b) => (b.resolved > a.resolved ? b : a), paidWithData[0]!)
export const topIndex = models.indexOf(top)
export const localAttempts = local.reduce((s, m) => s + m.attempts, 0)
export const localResolved = local.reduce((s, m) => s + m.resolved, 0)
export const gptOss = models.find((m) => m.id.includes('gpt-oss'))!
export const qwen3 = models.find((m) => m.id.includes('qwen3'))!

const fixByRepo = new Map<string, number>()
const topByRepo = new Map<string, [number, number]>()
for (const [mi, ii, , code] of attempts) {
  const repo = instances[ii]!.repo
  if (code === 1) fixByRepo.set(repo, (fixByRepo.get(repo) ?? 0) + 1)
  if (mi === topIndex) {
    const rec = topByRepo.get(repo) ?? [0, 0]
    rec[1] += 1
    if (code === 1) rec[0] += 1
    topByRepo.set(repo, rec)
  }
}
const lead = [...fixByRepo.entries()].sort((a, b) => b[1] - a[1])[0]!
export const leadRepo = lead[0]
export const leadFixes = lead[1]
export const leadRepoShort = repoShort(leadRepo)
export const topOnLead = topByRepo.get(leadRepo) ?? [0, 0]

const dates = instances.map((i) => i.merge_date).filter((d): d is string => d !== null).sort()
export const oldestDate = dates[0] ?? null
export const oldCount = dates.filter((d) => d < '2025-01-01').length

export const languages = Object.entries(dataset.languages).sort((a, b) => b[1] - a[1])
export const excludedTotal = models.reduce((s, m) => s + m.infra_excluded, 0)
export { totals, dataset, models, instances, attempts }

// Fixed by the harness (docs/fairness_contract.md, clause 3) and not read from the results file.
export const TURNS = 40
export const MINUTES = 15
