/** Shape of leaderboard/data/results.json, written by scripts/export_leaderboard_data.py. */

export interface Model {
  id: string
  name: string
  maker: string
  tier: 'paid' | 'local'
  note: string
  status: 'complete' | 'partial' | 'not_run'
  attempts: number
  planned_attempts: number
  resolved: number
  unresolved: number
  timeouts: number
  patch_apply_failed: number
  infra_excluded: number
  rate: number | null
  ci_low: number | null
  ci_high: number | null
  cost_usd: number
  cost_per_attempt: number | null
  instances_covered: number
  instances_total: number
}

export interface Instance {
  id: string
  repo: string
  language: string
  merge_date: string | null
  fail_to_pass: number
  pass_to_pass: number
}

/** [model index, instance index, repeat, outcome]. Outcome: 0 not fixed, 1 fixed, 2 timed out, 3 patch would not apply. */
export type Attempt = [number, number, number, 0 | 1 | 2 | 3]

export interface Results {
  generated_at: string
  dataset: { version: string; instances: number; repos: number; languages: Record<string, number> }
  totals: { attempts: number; resolved: number; models_with_data: number; cost_usd: number }
  models: Model[]
  instances: Instance[]
  attempts: Attempt[]
  smoke_test: { model: string; attempts: number; resolved: number; cost_usd: number }
}

export type ProblemTag = 'environment' | 'scoring' | 'supply' | 'infrastructure'

export interface Problem {
  id: string
  tag: ProblemTag
  title: string
  when: string
  symptom: string
  wrong_model: string
  cause: string
  fix: string
  lesson: string
  evidence: string
}

export type NodeGroup = 'client' | 'service' | 'core' | 'ops' | 'ship'

export interface ArchNode {
  id: string
  title: string
  sub: string
  group: NodeGroup
  x: number
  y: number
  w: number
  h: number
  role: string
  decisions: string[]
  files: string[]
  limitation?: string
  proof?: string
}

export interface ArchEdge {
  id: string
  from: string
  to: string
  d: string
  label?: string
  lx?: number
  ly?: number
  anchor?: 'start' | 'middle'
  kind: 'request' | 'control' | 'metrics' | 'return'
}

export interface TraceStep {
  node: string
  caption: string
}
