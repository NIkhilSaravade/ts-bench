import { Check, TriangleAlert } from 'lucide-react'
import Reveal from './Reveal'
import Section from './Section'
import { dataset, excludedTotal, gptOss, leadFixes, leadRepoShort, localAttempts, localResolved, oldCount, oldestDate, qwen3, top, topOnLead, TURNS, MINUTES } from '../lib/derived'
import { month, pct } from '../lib/format'
import { repoFile } from '../config'

/* ------------------------------------------------------------------ build order */

interface Milestone { id: string; title: string; built: string; result: string }

const MILESTONES: Milestone[] = [
  { id: 'T1', title: 'Foundation', built: 'A monorepo with uv, ruff, pre-commit and CI, and a validated task schema as the contract between every stage.', result: 'One valid and one malformed example, both checked by a test' },
  { id: 'T2', title: 'The language seam', built: 'Four methods that isolate everything language-specific, and a TypeScript adapter that maps test output to a canonical result.', result: 'zod 5,442 of 5,455, class-validator 743 of 743, trpc 114 of 114, identical across runs' },
  { id: 'T4', title: 'The task validator', built: 'The gold and empty gate: tests fail before the fix, pass after, over three runs, with every rejection logged.', result: '5 of 5 hand-picked zod tasks validated, none rejected' },
  { id: 'T6', title: 'Eval runner', built: 'Clean rebuild, restoring edited test files, a strict-then-fuzzy patch ladder, timeouts and a structured result.', result: 'Human fix resolves 5 of 5, empty patch 0 of 5, through the runner itself' },
  { id: 'T7', title: 'Reference agent', built: 'A deliberately minimal loop and a written fairness contract: fixed scaffold, prompt, budget, workspace and patch extraction.', result: 'With a real model: a clean fail, a partial fix and a genuine solve' },
  { id: 'T8', title: 'Model gateway', built: 'One LiteLLM interface for local and hosted models, a mock model that runs the whole loop offline, and the split between model and infrastructure failures.', result: 'A real billing failure was recorded as infrastructure, not as a lost attempt' },
  { id: 'T9', title: 'Statistics', built: 'pass@k with bootstrap error bars, checked against hand-derived cases before it touched real data.', result: 'Two independent runs reproduced the same ranking' },
  { id: 'T3', title: 'The miner', built: "A GitHub GraphQL miner using GitHub's own closing-issue links, cached and rate-limit aware.", result: '13 validated tasks across 3 repositories' },
  { id: 'T11', title: 'Rigor', built: 'Merge dates for contamination disclosure, and an audit that re-runs the gate several times to catch flaky or drifting tasks.', result: '13 of 13 clean over 78 fresh evaluations, when last run' },
  { id: 'T5', title: 'Dataset and Postgres', built: 'A versioned, immutable export and a schema that round-trips it exactly.', result: 'Loads with the datasets library and matches byte for byte in Postgres' },
  { id: 'T12', title: 'Docker sandbox', built: 'The same interface behind a container, with warm package-manager caches in volumes.', result: '13 of 13 through Docker. 25 to 35 percent faster on a monorepo' },
  { id: 'T13', title: 'Python adapter', built: 'A second language, in an isolated uv environment. It needed a small factory and one schema field, which the original plan had not predicted.', result: '5 tasks. 18 of 18 across two languages, no TypeScript regression' },
  { id: 'T14', title: 'Java adapter', built: 'A compiled language. Compile failures became a valid failing signal instead of a reason to discard a candidate.', result: `6 tasks, ${dataset.instances} across three languages` },
  { id: 'T15', title: 'Kafka and Kubernetes', built: 'An idempotent job queue and a three-pod consumer group.', result: '45 jobs, a killed pod redelivered exactly once, no duplicates' },
  { id: 'S7', title: 'First real models', built: 'Local Ollama models and a small paid tier, run through the full pipeline for the first time.', result: 'Eight bugs surfaced, and were fixed, only once real model output flowed through' },
  { id: 'T10', title: 'This site', built: 'Generated from the results, with the limits stated first.', result: 'Deploy and an outside reproduction check are still open' },
]

export function Journey() {
  return (
    <Section
      id="journey"
      title="How it was built, in order"
      intro="Fifteen tasks in dependency order, each finished only when its own check passed. The task board in the repository records what was actually built, including every bug on the way."
    >
      <ol className="timeline">
        {MILESTONES.map((s, i) => (
          <li key={s.id}>
            <Reveal delay={Math.min(i * 0.03, 0.15)} className="tl-row">
              <span className="tl-id num" aria-hidden="true">{s.id}</span>
              <div>
                <h3>{s.title}</h3>
                <p className="body">{s.built}</p>
                <p className="tl-result num">{s.result}</p>
              </div>
            </Reveal>
          </li>
        ))}
      </ol>
      <p className="small hint">Task ids match the task board, listed in the order they were actually built, which is not numeric order.</p>
    </Section>
  )
}

/* ------------------------------------------------------------------ tech stack */

const STACK: [string, string, string][] = [
  ['Language and packaging', 'Python 3.12, uv, hatchling', 'Core code, with locked and reproducible environments.'],
  ['Data and schema', 'Pydantic v2, JSONL, HuggingFace datasets', 'A validated task schema and a versioned, immutable dataset.'],
  ['Storage', 'PostgreSQL 16, psycopg 3', 'tasks, runs and results tables. Composite keys make replayed writes safe.'],
  ['Model access', 'LiteLLM, Ollama, OpenRouter, Anthropic API', 'One interface for local and hosted models, with cost and token logging.'],
  ['Targets under test', 'Node via nvm, pnpm, npm, yarn, vitest, jest, pytest, Maven, JUnit', "What the adapters drive inside each task's own repository."],
  ['Isolation', 'Docker, warm cache volumes, git archive', 'Runs without host state. Task folders are built with no git history.'],
  ['Scale-out', 'Apache Kafka 3.8 (KRaft), kafka-python, Kubernetes (kind)', 'An idempotent job queue and a pool of worker pods.'],
  ['Task sources', 'GitHub GraphQL API, bare git mirrors', 'Mining merged pull requests and extracting exact diffs.'],
  ['Agent experiment', 'LangChain, LangGraph', 'A tool-using second agent, kept in a separate project.'],
  ['Quality', 'pytest, ruff, pre-commit, GitHub Actions', '46 passing tests. CI enforces lint and formatting on every push, not the tests.'],
  ['This site', 'React 19, Vite, Tailwind, Motion, Cloudflare Pages', 'Static, with a strict content-security policy and no third-party requests.'],
]

export function Stack() {
  return (
    <Section
      id="stack"
      title="Tech stack"
      intro="About 4,500 lines of Python in the core. The choices are deliberately plain: each tool is there because a specific problem needed it."
    >
      <Reveal>
        <div className="tscroll">
          <table className="data stack">
            <thead><tr><th scope="col">Area</th><th scope="col">Tools</th><th scope="col">What they do here</th></tr></thead>
            <tbody>
              {STACK.map(([a, b, c]) => (
                <tr key={a}><th scope="row">{a}</th><td className="ink">{b}</td><td>{c}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Reveal>
    </Section>
  )
}

/* ------------------------------------------------------------------ verification */

const CHECKED: [string, string][] = [
  ['The human fix resolves every task and an empty patch none.', `${dataset.instances} of ${dataset.instances} through the local runner. All 13 TypeScript tasks also pass through Docker.`],
  ['Each task is deterministic.', 'Target tests must fail before the fix and pass after it, confirmed over three runs, with flaky tests dropped.'],
  ['The reliability audit came back clean.', '13 of 13 tasks, over 78 fresh evaluations, when it was last run.'],
  ['Cheating by editing tests is blocked.', 'A direct test tampers with a real test file and checks it is restored before scoring.'],
  ['The statistics are right.', 'pass@k and its error bars were checked against hand-derived cases before use.'],
  ['The queue never duplicates or loses a result.', 'A force-killed pod mid-job: 30 jobs gave exactly 30 rows.'],
  ['The scoring code is tested.', '46 automated tests pass, and CI checks lint and formatting on every push.'],
]

const NOT_CHECKED: [string, string][] = [
  ['No stranger has reproduced a number.', 'The steps are written down, but nobody outside this project has run them.'],
  ['The audit has not been re-run on all tasks.', `It last covered 13 of the ${dataset.instances}.`],
  ['Docker is verified for TypeScript only.', 'The Python and Java tasks were gated through the local runner.'],
  ['Several adapter paths have never met a real repository.', 'Gradle, poetry, uv, pipenv and mocha are implemented but untested.'],
  ['A syntax-broken TypeScript patch is not yet classified.', 'It has not happened in a real run, but the gap exists.'],
  ['The queue was only shown on the Python tasks.', 'Not the full set, and not at production scale.'],
]

export function Verification() {
  return (
    <Section
      id="verification"
      title="What has been checked, and what has not"
      intro="A claim is only worth as much as the check behind it. The left column is what was actually run. The right column is what was not, stated as plainly."
    >
      <div className="split">
        <Reveal>
          <h3 className="table-h">Checked</h3>
          <ul className="verify ok">
            {CHECKED.map(([a, b]) => (
              <li key={a}><Check size={18} aria-hidden="true" /><div><b>{a}</b><p className="small">{b}</p></div></li>
            ))}
          </ul>
        </Reveal>
        <Reveal delay={0.05}>
          <h3 className="table-h">Not checked</h3>
          <ul className="verify no">
            {NOT_CHECKED.map(([a, b]) => (
              <li key={a}><TriangleAlert size={18} aria-hidden="true" /><div><b>{a}</b><p className="small">{b}</p></div></li>
            ))}
          </ul>
        </Reveal>
      </div>
    </Section>
  )
}

/* ------------------------------------------------------------------ limitations */

export function Limitations() {
  const items: [string, string][] = [
    [`Only one model fixed anything, and only ${top.attempts} tries back it up.`, `${top.name} fixed ${top.resolved} of ${top.attempts}. With so few tries the honest range is ${pct(top.ci_low ?? 0)} to ${pct(top.ci_high ?? 0)}. It covers ${top.instances_covered} of ${top.instances_total} tasks because the paid budget ran out, and it got one attempt per task, so luck could move that number a lot.`],
    [`${leadFixes} of the ${top.resolved} fixes came from one project.`, `They are all in ${leadRepoShort}. ${top.name} fixed ${topOnLead[0]} of the ${topOnLead[1]} ${leadRepoShort} tasks it tried. That says the tasks in one repository were easier for it, not that it is good at every codebase.`],
    ['The free models scored zero, under one deliberately plain setup.', `Across ${localAttempts} attempts, the three local models fixed ${localResolved}. Their agent types one shell command per turn, with ${TURNS} turns and ${MINUTES} minutes. That does not prove these models cannot fix these bugs with better tooling. A separate tool-using agent, tried on 5 Python tasks with Qwen3 14B, fixed none either.`],
    ['Two planned models are incomplete or missing.', `${gptOss.name} was never run, so it has no score and is not shown as zero. ${qwen3.name} stopped at ${qwen3.attempts} of ${qwen3.planned_attempts} attempts, covering ${qwen3.instances_covered} of ${qwen3.instances_total} tasks.`],
    ["Older tasks may already be in a model's training data.", `${oldCount} of the ${dataset.instances} real fixes were merged before 2025, the oldest in ${month(oldestDate)}. Each model's training cutoff has not been recorded, so nothing here is labelled for contamination. That is a gap, not a clean bill.`],
    [`It is a small set: ${dataset.instances} tasks.`, `${dataset.repos} repositories. Java tasks are the hardest to build, and the set was grown by hand-checking candidates, not sampled at random.`],
    ['Local runs are not perfectly repeatable.', 'Local inference is not bit-for-bit reproducible even at temperature zero, so one task solved once in a timing test could not be reproduced in ten tries.'],
    [`${excludedTotal === 0 ? 'No attempts' : `${excludedTotal} attempts`} were excluded as infrastructure failures.`, 'That is because bad rows from the known incidents were removed and re-run before the numbers were exported, not because infrastructure never failed. The incidents are in the problem log above.'],
  ]
  return (
    <Section
      id="limitations"
      title="What these numbers cannot tell you"
      intro="This is an early, small run. It is honest about what it measured, and these are the reasons not to over-read it."
    >
      <Reveal>
        <ul className="limits">
          {items.map(([a, b]) => <li key={a}><b>{a}</b> {b}</li>)}
        </ul>
      </Reveal>
    </Section>
  )
}

/* ------------------------------------------------------------------ reproduce */

export function Reproduce() {
  const link = repoFile('docs/ts-bench-task-board.md')
  return (
    <Section
      id="reproduce"
      title="Reproduce it"
      intro="You need Docker, uv, and either Ollama or an API key. Nobody outside this project has run these steps yet, so treat them as untested by others."
    >
      <Reveal>
        <pre className="codeblock">
          <span className="c"># the human fix must resolve every task, an empty patch none</span>{'\n'}
          uv run python scripts/run_gate.py{'\n\n'}
          <span className="c"># run a model on every task, 10 tries each (resumable)</span>{'\n'}
          uv run python scripts/run_driver.py \{'\n'}
          {'  '}--models ollama_chat/qwen3:14b \{'\n'}
          {'  '}--instances all --repeats 10 \{'\n'}
          {'  '}--out results/my_run.jsonl{'\n\n'}
          <span className="c"># fix rate and pass@k with error bars</span>{'\n'}
          uv run python scripts/compute_stats.py --in results/my_run.jsonl --k 5
        </pre>
      </Reveal>
      <p className="note">
        The full build history, with every bug and its fix, is the task board{link ? <> at <a href={link} target="_blank" rel="noopener noreferrer"><code>docs/ts-bench-task-board.md</code></a></> : ''}.
      </p>
    </Section>
  )
}
