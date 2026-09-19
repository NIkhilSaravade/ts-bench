import type { ArchEdge, ArchNode } from '../types'

/** The language-adapter seam: a language-agnostic core, one interface, three implementations. */

export const SEAM_VIEW = { x: 0, y: -14, w: 1040, h: 530 } as const

export const SEAM_NODES: ArchNode[] = [
  {
    id: 'core', title: 'Core', sub: 'pipeline · harness · agent: no language-specific code', group: 'service', x: 20, y: 30, w: 1000, h: 88,
    role: 'Everything above the interface treats every language the same: mining, the validation gate, the eval runner, the sandbox and the agent.',
    decisions: [
      'If `if language ==` appears in core code, the seam is leaking. That was the test for every language added.',
      'The eval runner and validator only ever see a canonical map of test id to passed or failed.',
    ],
    files: ['harness/eval_runner.py', 'pipeline/validate.py', 'harness/language_adapter.py'],
    proof: 'Three languages run through the same gold and empty gate with the same code.',
  },
  {
    id: 'factory', title: 'get_adapter()', sub: 'one factory, keyed by language', group: 'ops', x: 380, y: 170, w: 280, h: 76,
    role: 'The single place that chooses an adapter class by name. Everywhere else is language-agnostic.',
    decisions: [
      'It was added when the second language arrived, because nothing had ever needed to choose an adapter before.',
      'Adding Java was one registered line here plus two schema allowlist entries.',
    ],
    limitation: 'The original plan promised zero core changes for a second language. That did not survive Python: it needed this factory and a schema field.',
    files: ['harness/adapters.py'],
  },
  {
    id: 'iface', title: 'LanguageAdapter', sub: 'detect · install · run_tests · parse', group: 'core', x: 240, y: 290, w: 560, h: 80,
    role: 'Four methods and two optional hooks. This is everything a new language has to provide.',
    decisions: [
      'detect_environment, install, run_tests and parse_results, always returning the same canonical test map.',
      'Two hooks with harmless defaults: is_compile_failure and extract_test_ids_from_diff, added for compiled languages.',
      'A schema field named node_version had leaked TypeScript into the shared schema. It was renamed runtime_version.',
    ],
    files: ['harness/language_adapter.py', 'pipeline/schema.py'],
  },
  {
    id: 'ts', title: 'TypeScript', sub: 'npm · pnpm · yarn · vitest · jest', group: 'client', x: 20, y: 410, w: 300, h: 88,
    role: 'Detects the package manager from the lockfile, pins the exact Node version, and reads test results from a JSON file.',
    decisions: [
      'Resolves the exact Node version through nvm and puts it first on PATH. It was recorded but never enforced before.',
      'Always writes vitest and jest output to an explicit file, because vitest does not reliably print JSON to stdout.',
      "Strips a repository's broken package-manager field and lifecycle scripts from the working copy, without touching dependency scripts.",
      'Runs the full suite from the workspace root and filters by path in Python: scoping a monorepo through the runner does not work.',
      'Forces npm workspace mode off, because a global .npmrc can otherwise break every install.',
    ],
    limitation: 'A patch that breaks syntax so badly that no test can start is not yet classified as a plain failure. It has not happened in a real run.',
    files: ['harness/ts_adapter.py'],
    proof: 'Verified on zod, class-validator, trpc, date-fns: same results across repeated runs.',
  },
  {
    id: 'py', title: 'Python', sub: 'uv venv · pytest', group: 'client', x: 370, y: 410, w: 300, h: 88,
    role: 'Builds an isolated environment with uv and reads a pytest JSON report.',
    decisions: [
      'A fresh uv venv per task, because the stdlib venv module is unavailable here without sudo.',
      'Installs the repository\'s test extra when one is declared, because tests import dependencies that are not base requirements.',
      'Sets a pretend version for setuptools-scm, which cannot work with no git history.',
      'Pytest exit code 4 means collection failed. It is scored against the model, not treated as an infrastructure error.',
    ],
    limitation: 'poetry, uv and pipenv installs are implemented but only plain pip has been exercised on a real repository.',
    files: ['harness/python_adapter.py'],
    proof: 'Verified on arrow and tenacity: 5 tasks.',
  },
  {
    id: 'java', title: 'Java', sub: 'Maven · JDK 17 · JUnit XML', group: 'client', x: 720, y: 410, w: 300, h: 88,
    role: 'Detects Maven or a repository\'s own Gradle wrapper, and reads the JUnit XML that Surefire already writes.',
    decisions: [
      'One modern JDK builds every project. The bytecode target comes from the project\'s own configuration, not from the JDK that runs the build.',
      'Builds multi-module repositories with a scoped reactor build, so unrelated sibling modules do not fail the run.',
      'Raises a typed compile-failure error, so a broken patch counts as not fixed and is never mislabelled as an infrastructure error.',
      'Treats a compile failure before the fix as a valid failing signal and reads test names from the diff.',
    ],
    limitation: 'Only Maven is verified on real repositories. The Gradle path is implemented but has never run.',
    files: ['harness/java_adapter.py', 'harness/test_outcomes.py'],
    proof: 'Verified on jsoup and JSON-java: 6 tasks, each hand-checked.',
  },
]

export const SEAM_EDGES: ArchEdge[] = [
  { id: 's1', from: 'core', to: 'factory', d: 'M520,118 V168', kind: 'request' },
  { id: 's2', from: 'factory', to: 'iface', d: 'M520,246 V288', kind: 'request' },
  { id: 's3', from: 'ts', to: 'iface', d: 'M170,410 V392 H380 V372', kind: 'control' },
  { id: 's4', from: 'py', to: 'iface', d: 'M520,410 V372', label: 'each implements it', lx: 392, ly: 386, kind: 'control' },
  { id: 's5', from: 'java', to: 'iface', d: 'M870,410 V392 H660 V372', kind: 'control' },
]
