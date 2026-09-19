import type { ArchEdge, ArchNode, TraceStep } from '../types'
import { dataset, TURNS, MINUTES } from '../lib/derived'

/** The system map: what each component is for, the decisions inside it, and where it lives in the repository. */

export const ARCH_VIEW = { x: 0, y: -14, w: 1040, h: 512 } as const

const W = 190
const H = 88
const C = [20, 290, 560, 830] as const
const R = [30, 214, 398] as const

export const NODES: ArchNode[] = [
  {
    id: 'sources', title: 'Sources', sub: 'GitHub API · git mirrors', group: 'client', x: C[0], y: R[0], w: W, h: H,
    role: 'Real fixes come from GitHub: merged pull requests that closed an issue and changed a test. One bare git mirror per repository is the source of truth for every diff and every checkout.',
    decisions: [
      "The miner reads GitHub's own closing-issue links, not a text search for 'fixes #N', so the issue-to-fix link is real.",
      'Every task is built from a mirror with git archive, never from a clone, so no history can leak into an agent\'s workspace.',
      'Search pages are cached to disk, so a re-run costs no API calls and stays inside rate limits.',
    ],
    files: ['pipeline/miner.py', 'pipeline/gitplumbing.py'],
    proof: `${dataset.repos} repositories, ${dataset.instances} tasks.`,
  },
  {
    id: 'pipeline', title: 'Task pipeline', sub: 'miner · validator', group: 'core', x: C[1], y: R[0], w: W, h: H,
    role: 'Turns candidates into checked tasks. A task is admitted only if its tests fail before the human fix and pass after it.',
    decisions: [
      'Each candidate is built fresh at the commit before the fix, with no git history.',
      'The target tests must fail, then pass, and the test sets come from three runs so flaky tests are dropped.',
      'Every rejection is logged with its reason. Nothing is silently discarded.',
      'For compiled languages, a compile failure before the fix counts as failing, with the test names read from the diff.',
    ],
    limitation: 'Yield varies a lot by language. Java needed a special path, and Apache projects that track issues in JIRA give no GitHub links at all.',
    files: ['pipeline/validate.py', 'pipeline/miner.py', 'scripts/mine_and_validate.py'],
    proof: `The human fix resolves all ${dataset.instances} tasks and an empty patch resolves none.`,
  },
  {
    id: 'taskset', title: 'Task set', sub: 'JSONL · versioned', group: 'client', x: C[2], y: R[0], w: W, h: H,
    role: 'The versioned, immutable set of tasks that every score is measured against.',
    decisions: [
      'A published version is never overwritten: the exporter refuses. A changed set gets a new version string.',
      'Each task carries its merge date in a sidecar file, so contamination risk can be disclosed.',
      'The JSONL loads directly with the HuggingFace datasets library.',
    ],
    limitation: 'Not yet published to the HuggingFace Hub. It lives in the repository.',
    files: ['pipeline/dataset_export.py', 'pipeline/schema.py', 'pipeline/contamination.py'],
    proof: `${dataset.version}: ${dataset.instances} tasks, ${Object.keys(dataset.languages).length} languages, ${dataset.repos} repositories.`,
  },
  {
    id: 'queue', title: 'Job queue', sub: 'Kafka · Kubernetes', group: 'service', x: C[3], y: R[0], w: W, h: H,
    role: 'Turns model, task and repeat into jobs that many workers pull in parallel.',
    decisions: [
      'Idempotent: the key is (run_id, instance_id, repeat), the same key the sequential driver uses. A replayed job is a no-op.',
      "The Kafka offset is committed only after the result is written, so a crashed worker's job is redelivered.",
      'A plain Deployment of three replicas. Kafka consumer-group rebalancing does the sharding.',
    ],
    limitation: 'Verified on a local kind cluster with one broker and only the Python tasks, not at production scale.',
    files: ['scripts/kafka_produce_jobs.py', 'scripts/kafka_worker.py', 'infra/k8s/worker-deployment.yaml'],
    proof: "Two runs of 15 and 30 jobs. A force-killed pod's job was redelivered exactly once: 30 jobs gave 30 rows.",
  },
  {
    id: 'gateway', title: 'Model gateway', sub: 'LiteLLM', group: 'ops', x: C[0], y: R[1], w: W, h: H,
    role: 'One interface for every model, local or hosted, so changing the model is a configuration change and never a code change.',
    decisions: [
      'Local Ollama, OpenRouter, Anthropic and a deterministic mock model all go through the same call.',
      'Output is capped per turn. The missing cap was why early runs seemed to hang.',
      'Cost and tokens come from each response. A billing or auth failure is recorded as an infrastructure error, not as a model failing to solve.',
    ],
    files: ['agent/loop.py', 'harness/driver.py', 'scripts/run_driver.py'],
    proof: 'A real billing failure during the paid smoke test was recorded as an infrastructure error, not a lost attempt.',
  },
  {
    id: 'agent', title: 'Agent scaffold', sub: 'one command per turn', group: 'core', x: C[1], y: R[1], w: W, h: H,
    role: 'A deliberately minimal loop held constant for every model, so score differences reflect the model and not the harness.',
    decisions: [
      'One plain-text shell command per turn, with no provider tool-calling API, so the identical request works against any model.',
      `A fixed budget: ${TURNS} turns and ${MINUTES} minutes.`,
      'Works in a private, throwaway workspace with its own git repository and none of the project\'s history.',
      'Ends a run that is provably stuck (the same command three times) and refuses an empty submit.',
    ],
    limitation: 'Deliberately weak: a fixed instrument, not a good agent. A smarter scaffold could score higher.',
    files: ['agent/loop.py', 'agent/workspace.py', 'agent/prompts.py', 'docs/fairness_contract.md'],
    proof: 'The fairness contract fixes scaffold, prompt, budget, workspace rules and patch extraction.',
  },
  {
    id: 'eval', title: 'Eval runner', sub: 'clean rebuild · score', group: 'core', x: C[2], y: R[1], w: W, h: H,
    role: "Scores one patch from scratch: a fresh copy, the agent's patch, the hidden tests, and the project's own test runner.",
    decisions: [
      'Test files the agent touched are restored before scoring, so it cannot pass by weakening tests.',
      'Hidden tests are added after the patch, so they always apply to pristine content.',
      'Fixed only if every target test passes and nothing else breaks.',
      'A patch that will not apply, or a compile failure, is a real not-fixed result and never a crash.',
    ],
    files: ['harness/eval_runner.py', 'harness/test_outcomes.py', 'pipeline/gitplumbing.py'],
    proof: 'Gold and empty gate through this runner: the human fix resolves every task, an empty patch none.',
  },
  {
    id: 'adapters', title: 'Language adapters', sub: 'TS · Python · Java', group: 'core', x: C[3], y: R[1], w: W, h: H,
    role: 'The only language-specific code. Each adapter knows how to detect, install, run tests and parse results for one language.',
    decisions: [
      'Four methods, so the core never branches on language.',
      'Adding Java took one registered line and two schema allowlist entries.',
      "Each adapter installs its own test reporter instead of assuming the repository has one.",
    ],
    limitation: 'Only Maven, pip and the npm family are verified on real repositories. Gradle, poetry, uv, pipenv and mocha are implemented but untested.',
    files: ['harness/adapters.py', 'harness/ts_adapter.py', 'harness/python_adapter.py', 'harness/java_adapter.py'],
    proof: `The seam holds across ${Object.keys(dataset.languages).length} languages and ${dataset.repos} repositories.`,
  },
  {
    id: 'site', title: 'Leaderboard site', sub: 'React · Cloudflare Pages', group: 'ship', x: C[0], y: R[2], w: W, h: H,
    role: 'This page. A static site built from the results data, with the limits stated first.',
    decisions: [
      'Every number is generated from the raw run files, not typed in.',
      'Static output with a strict content-security policy: no inline script and no third-party origin.',
      'Ranges and not just rates, because the sample is small.',
    ],
    files: ['leaderboard/data/results.json', 'scripts/export_leaderboard_data.py'],
    proof: 'A test checks that the exported data agrees with itself.',
  },
  {
    id: 'stats', title: 'Statistics', sub: 'Wilson · pass@k', group: 'ship', x: C[1], y: R[2], w: W, h: H,
    role: 'Turns attempts into honest numbers: a fix rate with an interval that stays sensible at zero, and pass@k with bootstrap error bars.',
    decisions: [
      'Wilson intervals, because a plain standard error collapses to zero at 0 of n and would make the local models look falsely certain.',
      'pass@k uses the unbiased estimator, checked against hand-derived cases before it was trusted.',
      'Errors on our side are excluded from the denominator. Timeouts and patches that will not apply stay in it.',
    ],
    limitation: 'Real models mostly have one attempt per task, so pass@k and variance are not reported for them.',
    files: ['pipeline/stats.py', 'scripts/compute_stats.py', 'scripts/export_leaderboard_data.py'],
  },
  {
    id: 'store', title: 'Results store', sub: 'Postgres', group: 'client', x: C[2], y: R[2], w: W, h: H,
    role: 'Every attempt as a row, keyed so that a result is only ever valid against one exact task-set version.',
    decisions: [
      'A composite key of instance and dataset version on tasks, which results reference.',
      'One results row per run, task and repeat, mirroring the runner\'s result type.',
      'Loaders are idempotent and read everything back to check it matches the source.',
    ],
    files: ['infra/schema.sql', 'pipeline/db.py', 'scripts/load_results.py'],
    proof: 'The 647 free-model rows loaded and matched the source file exactly.',
  },
  {
    id: 'sandbox', title: 'Sandbox', sub: 'local · Docker', group: 'service', x: C[3], y: R[2], w: W, h: H,
    role: 'Runs a command with a real timeout, on the same folder, whether locally or in a container.',
    decisions: [
      'A narrow interface: run a command with a timeout. Building the files stays outside it.',
      "Docker keeps the package managers' caches warm in volumes and always runs the install in full.",
      'The container sees the folder at the same path as the host, so parsed test paths still match.',
    ],
    files: ['harness/local_sandbox.py', 'harness/docker_sandbox.py'],
    proof: 'The gate passes identically through Docker on all 13 TypeScript tasks. Warm installs were 25 to 35 percent faster on a monorepo.',
  },
]

export const EDGES: ArchEdge[] = [
  { id: 'e1', from: 'sources', to: 'pipeline', d: 'M210,74 H288', label: 'mine', lx: 232, ly: 64, kind: 'request' },
  { id: 'e2', from: 'pipeline', to: 'taskset', d: 'M480,74 H558', label: 'export', lx: 500, ly: 64, kind: 'request' },
  { id: 'e3', from: 'taskset', to: 'queue', d: 'M750,74 H828', label: 'jobs', lx: 776, ly: 64, kind: 'request' },
  { id: 'e4', from: 'queue', to: 'agent', d: 'M925,118 V166 H385 V212', label: 'run job', lx: 640, ly: 158, kind: 'request' },
  { id: 'e5', from: 'agent', to: 'gateway', d: 'M288,258 H212', label: 'prompt', lx: 228, ly: 246, kind: 'control' },
  { id: 'e6', from: 'agent', to: 'eval', d: 'M480,258 H558', label: 'patch', lx: 500, ly: 246, kind: 'request' },
  { id: 'e7', from: 'eval', to: 'adapters', d: 'M750,258 H828', label: 'run tests', lx: 764, ly: 246, kind: 'control' },
  { id: 'e8', from: 'adapters', to: 'sandbox', d: 'M925,302 V396', label: 'execute', lx: 935, ly: 354, kind: 'control' },
  { id: 'e9', from: 'eval', to: 'store', d: 'M655,302 V396', label: 'result', lx: 665, ly: 354, kind: 'request' },
  { id: 'e10', from: 'store', to: 'stats', d: 'M558,442 H480', label: 'export', lx: 500, ly: 432, kind: 'request' },
  { id: 'e11', from: 'stats', to: 'site', d: 'M288,442 H212', label: 'render', lx: 228, ly: 432, kind: 'request' },
]

export const TRACE: TraceStep[] = [
  { node: 'sources', caption: 'A merged pull request that closed a GitHub issue and changed a test is found, along with the commit just before it merged.' },
  { node: 'pipeline', caption: 'The commit is rebuilt with no history. The new tests must fail, the human fix must make them pass, and three runs drop flaky tests.' },
  { node: 'taskset', caption: 'The task, its issue text, its hidden tests and its merge date are written into the versioned task set.' },
  { node: 'queue', caption: 'A job for one model, one task and one repeat is queued. A worker pulls it. If the same job arrives twice, the second is skipped.' },
  { node: 'agent', caption: 'The agent gets the issue text in a private workspace with no git history, and tries to write a patch within its fixed budget.' },
  { node: 'eval', caption: "The patch is scored on a clean rebuild. Test files it edited are restored, hidden tests are added, and the project's own runner decides, through a language adapter, in a sandbox." },
  { node: 'store', caption: 'The outcome is written once, keyed by run, task and repeat, with cost, tokens and time.' },
  { node: 'stats', caption: 'Attempts become a fix rate with a 95% range, and pass@k where there are repeats. Our own failures are left out.' },
  { node: 'site', caption: 'The page you are reading is generated from those numbers.' },
]

export const GROUPS = ['client', 'service', 'core', 'ops', 'ship'] as const
