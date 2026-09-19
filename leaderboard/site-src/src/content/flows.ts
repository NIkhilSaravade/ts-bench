import type { REdge, RNode, Scenario } from '../components/Replay'
import type { Step } from '../components/Stepper'

/* ------------------------------------------------------------------ the life of a task (the gold and empty gate) */

export const TASK_VIEW = '0 0 1010 300'

export const TASK_NODES: RNode[] = [
  { id: 'candidate', x: 20, y: 60, w: 140, label: 'Candidate', sub: 'merged PR' },
  { id: 'materialize', x: 190, y: 60, w: 150, label: 'Materialize', sub: 'no git history' },
  { id: 'red', x: 370, y: 60, w: 140, label: 'Red run', sub: 'tests must fail' },
  { id: 'green', x: 540, y: 60, w: 140, label: 'Green run', sub: 'must now pass' },
  { id: 'derive', x: 710, y: 60, w: 130, label: 'Derive sets', sub: 'three runs' },
  { id: 'accepted', x: 870, y: 60, w: 120, label: 'ACCEPTED', sub: 'in the task set' },
  { id: 'rejected', x: 500, y: 200, w: 240, label: 'REJECTED', sub: 'logged with a reason', group: 'ship' },
]

export const TASK_EDGES: REdge[] = [
  { d: 'M160,92 H188' },
  { d: 'M340,92 H368' },
  { d: 'M510,92 H538' },
  { d: 'M680,92 H708' },
  { d: 'M840,92 H868' },
  { d: 'M440,124 V160 H560 V198', kind: 'control', label: 'already passes', lx: 448, ly: 150 },
  { d: 'M610,124 V198', kind: 'control', label: 'still fails', lx: 622, ly: 178 },
  { d: 'M775,124 V160 H700 V198', kind: 'control', label: 'nothing stable', lx: 780, ly: 150 },
]

export const TASK_SCENARIOS: Scenario[] = [
  {
    id: 'ok', label: 'Accepted',
    path: ['candidate', 'materialize', 'red', 'green', 'derive', 'accepted'],
    caption: "The pull request's new tests fail on the code before the fix, pass once the human fix is applied, and give the same answer on three runs. The task is written to the set with its fail_to_pass and pass_to_pass lists.",
  },
  {
    id: 'nobug', label: 'No bug at base',
    path: ['candidate', 'materialize', 'red', 'rejected'],
    caption: 'The target tests already pass before the fix, so there is no bug to fix or the tests do not test it. The candidate is rejected and the reason is logged.',
  },
  {
    id: 'incomplete', label: 'Fix incomplete',
    path: ['candidate', 'materialize', 'red', 'green', 'rejected'],
    caption: 'The tests still fail with the human fix applied. Either the fix is incomplete or the environment is wrong, and either way the task cannot be trusted.',
  },
  {
    id: 'flaky', label: 'Flaky',
    path: ['candidate', 'materialize', 'red', 'green', 'derive', 'rejected'],
    caption: 'A test that gives different answers across the three runs is dropped from the sets. If no deterministic target test remains, the whole candidate is rejected.',
  },
  {
    id: 'compiled', label: 'Compiled language',
    path: ['candidate', 'materialize', 'red', 'red', 'green', 'derive', 'accepted'],
    caption: 'In Java the new tests often call a method the fix adds, so they cannot compile before the fix. That counts as failing, and the test names are read from the diff. The green run must still prove them, so a wrong guess can only miss a task, never approve a false one.',
  },
]

/* ------------------------------------------------------------------ scoring one attempt */

export const SCORING_STEPS: readonly Step[] = [
  { name: 'Rebuild', code: 'materialize_instance()', text: 'A new copy of the commit before the fix, into a plain folder with no .git. There is no history to look anything up in.' },
  { name: 'Install', code: 'adapter.install()', text: 'Dependencies at the exact runtime version. An install failure is an infrastructure error, unless it is a compile failure, which is a real result.' },
  { name: 'Reset tests', code: 'restore_paths()', text: 'Any test file the agent touched is restored from the pristine mirror, and any it invented is deleted. This is what stops an agent passing by weakening tests.' },
  { name: 'Apply patch', code: 'try_apply_patch()', text: 'Strict first, then fuzzy. A diff that will not apply scores as not fixed and never crashes the run.' },
  { name: 'Hidden tests', code: 'test_patch', text: "The project's real tests for this bug are added last, so they always apply to pristine content and the agent can never edit them." },
  { name: 'Run', code: 'adapter.run_tests()', text: 'The whole suite in the sandbox, with a timeout. Results are filtered to the target tests in Python, because scoping a runner to named tests is unreliable.' },
  { name: 'Score', code: 'resolve_test_outcome()', text: 'Fixed only if every fail_to_pass and pass_to_pass test passes. A parameterised test passes only if every variant of it does.' },
]

/* ------------------------------------------------------------------ the job queue */

export const SCALE_VIEW = '0 0 1000 330'

export const SCALE_NODES: RNode[] = [
  { id: 'producer', x: 20, y: 120, w: 150, label: 'Producer', sub: 'model × task × repeat', group: 'service' },
  { id: 'topic', x: 210, y: 120, w: 160, label: 'Kafka topic', sub: '6 partitions', group: 'service' },
  { id: 'w1', x: 430, y: 30, w: 150, label: 'Worker 1', sub: 'pod', group: 'core' },
  { id: 'w2', x: 430, y: 130, w: 150, label: 'Worker 2', sub: 'pod', group: 'core' },
  { id: 'w3', x: 430, y: 230, w: 150, label: 'Worker 3', sub: 'pod', group: 'core' },
  { id: 'db', x: 760, y: 120, w: 210, label: 'Postgres', sub: 'run · task · repeat', group: 'client' },
]

export const SCALE_EDGES: REdge[] = [
  { d: 'M170,152 H208' },
  { d: 'M370,140 C400,140 400,62 428,62' },
  { d: 'M370,158 H428' },
  { d: 'M370,176 C400,176 400,262 428,262' },
  { d: 'M580,62 C680,62 680,138 758,138' },
  { d: 'M580,162 H758' },
  { d: 'M580,262 C680,262 680,180 758,180' },
]

export const SCALE_SCENARIOS: Scenario[] = [
  {
    id: 'normal', label: 'One job',
    path: ['producer', 'topic', 'w1', 'db'],
    caption: 'A worker pulls a job, checks Postgres for its key, runs the agent and the eval runner in a sandbox, inserts the result once, and only then commits the Kafka offset.',
  },
  {
    id: 'dup', label: 'Replayed job',
    path: ['producer', 'topic', 'w2', 'db'],
    caption: 'The same message arrives a second time. The worker finds the key already in Postgres, skips the work, and commits the offset. No second row, and no second charge for an API call.',
  },
  {
    id: 'kill', label: 'Pod killed',
    path: ['producer', 'topic', 'w2', 'topic', 'w3', 'db'],
    caption: 'Worker 2 is force-killed mid-job. Its offset was never committed, so Kafka redelivers the job and Worker 3 completes it. In the real test, 30 jobs produced exactly 30 rows.',
  },
]
