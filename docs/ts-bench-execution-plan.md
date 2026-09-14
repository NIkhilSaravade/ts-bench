# TS-Bench — Detailed Execution Plan

> A dependency-ordered build plan. No dates — do the steps in order, because each one unlocks the next.
> Every step has the same shape:
> **Goal · Why (first principles) · Build · Learn · Research · Done-when (test) · Pitfalls.**
> "Done-when" is a *test you can run to prove the step is actually finished* — treat it as a gate, not a suggestion.

---

## How to use this plan

Three rules that will save you from the two most common ways benchmark projects die:

1. **Never advance past a "Done-when" gate on hope.** If the gate says "the gold patch resolves and the empty patch fails," and it doesn't, you have a bug in your harness — not a reason to move on. A benchmark built on an unverified harness is worthless, and worse, *confidently* worthless.
2. **Build the multi-language seam early, but ship one language.** The plan bakes in the adapter interface (Stage B) so Java/Python are later drop-ins, but Stages C–H are all pure TypeScript. Resist scope creep.
3. **Curation is the project.** Stages C and F (data + rigor) are where the credibility lives and where most of your hours go. The agent and the leaderboard are the easy, visible 20%. Don't let the visible parts eat the time the invisible parts need.

The stages:
- **A** — Orient yourself in existing benchmarks
- **B** — The language-adapter seam (design multi-lang, implement TS)
- **C** — Data pipeline (mine → validate → package tasks)
- **D** — Execution harness (sandbox → apply → run → score)
- **E** — Agent + model dimension
- **F** — Rigor hardening (what makes it credible)
- **G** — Scale
- **H** — Leaderboard + launch
- **I** — Multi-language expansion (v2)

---

# STAGE A — Orientation

## Step 1 — Run an existing benchmark end to end, before building anything

**Goal.** Reproduce a real evaluation on SWE-bench Lite with your own hands and eyes, on ~5 instances, using a cheap model.

**Why (first principles).** You cannot design a harness you've never seen run. Every abstraction in this project — task instance, patch, fail-to-pass, layered images — is obvious *after* you watch one task flow through, and confusing before. Reproducing prior art first means you copy proven design instead of inventing broken design. This is the single highest-leverage hour in the whole project.

**Build.** Nothing yet. Clone SWE-bench, install its harness, run `run_evaluation` on a handful of instances with a gold-patch prediction and with one cheap model's prediction.

**Learn.**
- The task-instance schema cold (repo, base_commit, problem_statement, test_patch, FAIL_TO_PASS, PASS_TO_PASS, gold_patch).
- Why evaluation runs in Docker and what "layered images" buys you.
- What "resolved" means precisely, and how it's computed.

**Research.**
- SWE-bench (original paper) — the paradigm.
- SWE-bench Verified — the human-validated subset and *why* it exists (task quality is hard).
- SWE-bench Multilingual + CLAW-SWE-BENCH — how the same core extends across languages, and the "score conflates model × harness × task" argument. Read CLAW twice.
- Terminal-Bench — how a leaderboard cleanly separates model from scaffold.
- How each leaderboard *reports*: resolved %, cost, pass@k.

**Done-when.** You can (a) run the SWE-bench harness on 5 instances and get scores, (b) verify a gold patch resolves and an empty patch does not, and (c) explain the full loop to someone else without notes.

**Pitfalls.** Docker disk/CPU limits will bite immediately; sort them now while stakes are low. Don't try to read *all* the code — trace exactly one instance through the harness.

---

# STAGE B — The language-adapter seam

## Step 2 — Project skeleton, environment, and the task schema as code

**Goal.** A clean repo with a reproducible Python environment, Docker wired in, Postgres running locally, and the task instance modeled as validated code.

**Why.** The schema is the contract every later stage depends on. If it's sloppy, every downstream bug is a schema bug in disguise. Defining it first — as a real, validated type — forces you to be precise about what a task *is*.

**Build.**
- Monorepo layout: `pipeline/` (mining+validation), `harness/` (execution), `agent/` (reference scaffold), `leaderboard/` (site), `datasets/`, `infra/`.
- Python env with `uv` or `poetry`; lint/format (ruff), pre-commit, minimal CI.
- `docker` available; a local Postgres via docker-compose.
- The task instance as a `pydantic` model (or JSON Schema) + a hand-written example instance file.

**Learn.**
- Modern Python project hygiene (envs, packaging, lockfiles) — this is new for a Java person and worth doing right once.
- Pydantic/JSON-Schema validation.

**Research.** How SWE-bench stores instances (JSONL on HuggingFace) so your schema stays compatible with existing tooling — compatibility is a feature, not a constraint.

**Done-when.** Your schema validates a hand-authored example task and *rejects* a deliberately malformed one; CI runs lint on every push.

**Pitfalls.** Don't gold-plate the repo structure. A skeleton that runs beats a perfect layout that doesn't.

## Step 3 — Define the `LanguageAdapter` interface

**Goal.** A four-method interface that isolates *everything language-specific* behind one seam.

**Why (first principles).** ~90% of a code-agent benchmark is language-agnostic: a git diff, a container, "tests that fail before and pass after," a score. Only four things actually depend on the language. Naming that boundary now is what makes Java and Python later a *drop-in* rather than a rewrite. Get the seam right and multi-language is free; get it wrong and you'll refactor the whole harness.

**Build.** An interface with exactly these methods:
1. `detect_environment(repo)` → language version, package manager, test runner.
2. `install(container)` → get dependencies installed reproducibly.
3. `run_tests(container, test_ids)` → execute tests.
4. `parse_results(raw_output)` → map runner output to `{test_id: pass|fail}`.
Plus a stub `TypeScriptAdapter` that raises `NotImplemented`.

**Learn.** Interface/adapter design; why the core must never branch on language (`if lang == "java"` anywhere in the core is a design smell).

**Research.** How CLAW-SWE-BENCH / SWE-bench-Multilingual structure per-language support — you're re-deriving a proven pattern.

**Done-when.** The core eval loop (written later) type-checks against the *interface*, never a concrete adapter. You can articulate why each of the four methods is language-specific and why nothing else is.

**Pitfalls.** Over-abstracting. Four methods is the target; if you're adding a fifth, ask whether it's really language-specific or just leaking harness logic into the adapter.

## Step 4 — Implement `TypeScriptAdapter`

**Goal.** A working TS adapter that installs deps, runs tests, and — the hard part — reliably tells you *which named tests* passed or failed.

**Why.** Your entire success signal (FAIL_TO_PASS / PASS_TO_PASS) is "did *these specific* tests pass?" If you can't map runner output to individual test IDs deterministically, you have no benchmark. This step is fiddlier than it looks and deserves real care.

**Build.**
- Package-manager detection (npm / pnpm / yarn from lockfiles).
- Node version pinning.
- Test-runner detection (vitest / jest / mocha) and invocation with a **machine-readable reporter** (`--reporter=json` / `--json`).
- A parser that turns that JSON into `{test_id: pass|fail}`, stable across runs.

**Learn.**
- The TS toolchain in depth: lockfiles, workspaces/monorepos, node version managers.
- The JSON output formats of vitest and jest — they differ, and test-ID naming is subtly inconsistent.
- Optional TS-only signals: `tsc --noEmit` (typecheck) and eslint as *extra* verification dimensions Python benchmarks can't offer — a genuine differentiator to note in your writeup.

**Research.** Real repos' test configs; how monorepo repos scope a single package's tests; how flaky/async tests surface in reporter output.

**Done-when.** Point the adapter at 2–3 different TS repos (one vitest, one jest, ideally one monorepo) and get a correct, stable pass/fail map for named tests every run.

**Pitfalls.** Test-ID instability (same test, different string across runs) silently corrupts FAIL_TO_PASS matching. Nail down a canonical test-ID format now.

---

# STAGE C — Data pipeline (mine → validate → package)

## Step 5 — Repo selection

**Goal.** A shortlist of TypeScript repos worth mining, each with a written rationale.

**Why.** Task quality is capped by repo quality. A repo with flaky tests, exotic build steps, or no issue↔PR discipline will waste enormous validation effort for few usable tasks. Choosing well *is* the work.

**Build.** A selection doc scoring candidates on: active maintenance, strong test suite, standard runner, permissive license, clear "issue → fixing PR with a test" pattern, reasonable build time.

**Learn.** What makes a repo minable; license implications for redistributing task data (you're packaging references to their code/tests — understand what you can publish).

**Research.** Candidate repos (utility/library repos are easiest to start: strong tests, fast builds, clean issues). Manually inspect a few merged PRs in each to confirm the "PR adds a test that proves the fix" pattern actually holds there.

**Done-when.** You've *manually* cloned each shortlisted repo, installed it, and run its test suite green. If it doesn't build clean by hand, it won't mine clean.

**Pitfalls.** Picking a huge framework first (slow builds, complex setup). Start small and well-tested; scale repo size later.

## Step 6 — PR/issue mining

**Goal.** A miner that emits candidate tasks: (repo, fixing-PR, linked-issue, base_commit).

**Why.** You need *real* human-accepted fixes with tests. A merged PR that closes an issue and modifies a test file is the raw material for a fail-to-pass task. Mining automates finding those candidates so humans (your validator) only judge the promising ones.

**Build.** A GitHub miner that, per repo, finds merged PRs where: the PR closes an issue (`fixes #N` / `closes #N` linkage), and the PR's diff touches test files. Output raw candidates to storage.

**Learn.** GitHub REST + GraphQL APIs; rate limits and pagination; how issue↔PR linkage is represented; how to classify "test file" per repo conventions.

**Research.** How SWE-bench detects issue-linked PRs and test-touching diffs; GraphQL for efficient PR/issue traversal (fewer calls than REST).

**Done-when.** Run the miner on one repo and hand-verify a sample of candidates — each really is an issue-closing PR that changed tests.

**Pitfalls.** Rate limits will throttle you; cache aggressively and use GraphQL. Not every "closes #N" is a real bug fix (some are features/refactors) — that's fine, the next step filters hard.

## Step 7 — Task validation & instance construction (the crucial step)

**Goal.** Turn raw candidates into *verified* task instances — or reject them. This is the heart of the whole project.

**Why (first principles).** A task is only valid if it's *objectively solvable and objectively checkable*. That means: at the base commit, the fix's tests genuinely fail (the bug is real and unsolved); with the human fix applied, they genuinely pass (the fix is real). If either isn't true, the "task" is noise that will produce meaningless scores. This gold/empty logic is what separates a benchmark from a pile of GitHub links.

**Build.** A validator that, per candidate:
1. Checks out `base_commit`; strips later history and the git remote (anti-leakage).
2. Installs deps (via the adapter).
3. Runs the PR's added/changed tests → they must **FAIL**. (If they pass at base, there's no bug — reject.)
4. Applies the gold patch → those tests must **PASS**. (If not, the fix is incomplete or the setup is wrong — reject.)
5. Derives `FAIL_TO_PASS` (failed→passed) and `PASS_TO_PASS` (already passing, still passing — the regression guard).
6. Emits a clean, schema-valid task instance; otherwise records a rejection reason.

**Learn.** Git plumbing (checkout, diff, apply, resetting test files, removing remotes); the precise definitions of FAIL_TO_PASS vs PASS_TO_PASS; how to detect and quarantine flaky tests during validation.

**Research.** SWE-bench's exact FAIL_TO_PASS/PASS_TO_PASS computation; flaky-test handling strategies (run N times, keep only deterministic ones); how contamination-conscious datasets pick commit windows.

**Done-when.** Every emitted instance passes the **gold-passes / empty-fails** gate: gold patch → resolved, empty patch → not resolved. You have **5–10 rock-solid validated instances from one repo**, and a rejection log you understand.

**Pitfalls.** This is where hidden nondeterminism lives — a test that "sometimes fails" will pollute your set. Be ruthless: when in doubt, reject. Ten clean tasks beat fifty shaky ones.

## Step 8 — Dataset packaging & storage

**Goal.** Persist validated tasks in a standard, versioned, queryable form.

**Why.** Tasks are your ground truth; they must be reproducible and shareable (others need the exact same set to compare fairly). Two homes: a portable dataset artifact + a relational store for runs/results.

**Build.**
- Export instances as JSONL / HuggingFace `datasets` (with a version tag).
- Postgres schema: `tasks`, `runs` (a model/agent × config execution), `results` (per-task outcome), `models`.

**Learn.** HuggingFace datasets + versioning; relational modeling for eval results (you're strong here).

**Done-when.** You can load the published dataset fresh and round-trip it into Postgres; task set has an immutable version identifier.

**Pitfalls.** Not versioning the dataset. Scores are only comparable against a *fixed* task set — "TS-Bench v0.1" must mean one exact set forever.

---

# STAGE D — Execution harness

## Step 9 — Container / image strategy

**Goal.** Reproducible, cached, layered Docker images so every run of a task is identical and fast.

**Why (first principles).** A score must mean the same thing on your laptop, a CI runner, and a stranger's machine — that requires freezing the OS, runtime, and deps in an image. Layering (shared base → per-repo env → per-commit instance) makes thousands of runs affordable by caching the expensive parts.

**Build.** Three image layers, à la SWE-bench: **base** (OS + node + package managers), **environment** (one per repo, deps installed), **instance** (repo at a base_commit). A builder + a local registry/cache.

**Learn.** Docker layer caching, image-size management, reproducible builds, registry basics.

**Research.** SWE-bench's image architecture and how they pin environments deterministically.

**Done-when.** Rebuilding an instance image is cache-fast; the *same* task yields the *same* test results across two different machines.

**Pitfalls.** Non-pinned deps (`latest` tags, unpinned transitive versions) reintroduce nondeterminism you worked hard to remove. Pin everything.

## Step 10 — The eval runner  · ✅ Done (v0.1) — see task board T6

**Goal.** Orchestrate a full evaluation of one (task, agent-output) pair and produce a result.

**Why.** This is the loop the whole benchmark exists to run. It must be airtight, because every scoring subtlety (test-file tampering, patch-apply failures, timeouts) lives here.

**Build.** *(v0.1 note, added after T6: the actual v0.1 implementation used a from-scratch, no-isolation `LocalSandbox` — plain `subprocess.Popen` with a real timeout/kill — instead of the code-execution platform. Real reuse of that platform is deferred to the Docker sandbox upgrade below, which is this same step's "Step 9/20" hand-off point on the task board's "After v0.1" list. See `claude/ts-bench-task-board.md`'s T6 notes for the full reasoning and what actually got built.)* Reuse your code-execution platform as the sandboxed runner. The loop:
1. Spin up the instance container (repo @ base_commit, history/remote stripped).
2. Present the agent the problem_statement + repo access.
3. Collect the agent's patch (git diff).
4. **Reset any test files the agent touched** (it must not weaken tests), then apply the agent's patch.
5. Apply *your* test_patch on top.
6. Run FAIL_TO_PASS + PASS_TO_PASS under a strict timeout.
7. Emit a structured result.

**Learn.** Sandbox orchestration; patch-application edge cases (fuzz, conflicts, malformed diffs); timeout/kill handling; capturing stdout/stderr for debugging.

**Research.** How SWE-bench sanitizes agent edits and extracts patches; common patch-apply failure modes.

**Done-when.** End-to-end **gold/empty gate through the full runner**: feeding the gold patch resolves every task; feeding an empty patch resolves none. This proves the *runner* (not just the validator) is correct.

**Pitfalls.** Forgetting step 4 (test-file reset) lets an agent "solve" tasks by editing the tests — a silent correctness hole. Also: an agent producing a non-applying diff should score *unresolved*, not crash the run.

## Step 11 — Scoring & result recording  · ✅ Done (v0.1) — see task board T6

**Goal.** Turn raw test outcomes into scores + full run metadata.

**Why.** "Resolved" is the headline, but cost, tokens, and wall-clock are what make results *comparable and honest*. Capture them from day one; retrofitting is painful.

**Build.** Resolved logic (all FAIL_TO_PASS pass AND all PASS_TO_PASS pass); capture cost, tokens, latency; write structured results to Postgres. *(v0.1 note: results currently live in an in-memory `EvalResult` dataclass, not Postgres yet — that lands with Step 8/T5. `cost_usd`/`tokens_used` are already nullable fields on it, ready for T8 to populate.)*

**Learn.** Metric definitions; per-run cost accounting.

**Done-when.** Scores on your validated set match manual expectation; every result row carries cost/tokens/time.

**Pitfalls.** Reporting only resolved % without cost invites unfair comparisons (a model that spends 10× to win looks equal). Record cost now.

---

# STAGE E — Agent + model dimension

## Step 12 — Decide what your leaderboard isolates

**Goal.** Consciously choose: a *model* leaderboard (Option A) or an *agent/scaffold* leaderboard (Option B). Start with A.

**Why (first principles).** A raw resolved-rate conflates three causes — the model, the harness/scaffold, and the tasks. If you don't fix two of them, your number measures nothing attributable. Option A fixes the harness and tasks and varies only the model — the cleanest science and the easiest to run solo.

**Build.** A written **fairness contract**: fixed reference scaffold, fixed prompt, fixed token + wall-clock budget, fixed workspace rules, fixed patch-extraction. This paragraph is what makes reviewers trust you.

**Learn/Research.** The CLAW-SWE-BENCH isolation argument; how mini-swe-agent / SWE-agent / Aider / OpenHands differ as scaffolds.

**Done-when.** Your fairness contract is written down and lives in the README.

**Pitfalls.** Trying to launch Option B (open scaffold submissions) first — it multiplies the fairness surface before you've earned trust with a clean Option A.

## Step 13 — Build (or adopt) a reference agent scaffold

**Goal.** A minimal, deterministic-as-possible agent that takes (problem, repo) and returns a patch.

**Why.** In Option A this scaffold is a *fixed instrument* — held constant so differences reflect the model. Minimal is a feature: fewer moving parts, more attributable results.

**Build.** A basic explore→edit→submit loop via LiteLLM: read the problem, inspect relevant files, propose edits, emit a git diff. Study `mini-swe-agent` for the simplest credible design.

**Learn.** Agent scaffolding fundamentals: the observe/act loop, tool use, context-window management, patch extraction, enforcing budgets.

**Research.** Prompt design for code-fix agents; how minimal scaffolds keep context small; failure modes (hallucinated file paths, non-applying diffs).

**Done-when.** On your validated tasks the reference agent *sometimes* solves and *sometimes* fails — a scaffold that scores 0% or 100% signals a broken harness or trivial/impossible tasks.

**Pitfalls.** Over-engineering the agent. In Option A the agent is a constant, not the star; keep it simple and stable.

## Step 14 — Model runner via LiteLLM

**Goal.** Swap models behind one uniform interface, with budgets, retries, and cost logging.

**Why.** "Vary only the model" must be a config change, not a code change — that's exactly what a model gateway gives you, and you already know LiteLLM.

**Build.** A runner that drives the reference agent with any provider via LiteLLM; enforces budgets; logs cost/tokens; handles rate limits and retries.

**Learn.** LiteLLM in depth; provider quirks (tool-use formats, context limits); cost control.

**Done-when.** You run the same tasks across 3–4 models with identical scaffold/budget and get comparable, logged results.

**Pitfalls.** Silent budget/rate-limit failures scoring as "unresolved" and skewing a model down. Distinguish "agent failed to solve" from "infra failed to run."

## Step 15 — First real results

**Goal.** Your first honest scores: resolved % + pass@k + variance + cost, per model.

**Why (first principles).** LLMs are stochastic; a single run per task is a coin flip reported as a fact. Running each task k times and reporting pass@k (and variance) is the difference between a result and an anecdote.

**Build.** Run each task k times per model; compute resolved %, pass@k, variance, total cost.

**Learn.** pass@k; how stochasticity inflates/deflates single-run numbers; honest statistical reporting.

**Done-when.** Re-running the whole matrix reproduces the same ranking within stated variance.

**Pitfalls.** Reporting k=1 numbers as if they were stable. Anyone who knows evals will spot it instantly.

---

# STAGE F — Rigor hardening (this is the credibility)

## Step 16 — Contamination controls

**Goal.** Minimize the chance a model simply *memorized* the fix from training data.

**Why.** If a model saw the repo's post-fix history during training, a high score measures recall, not reasoning. Credible benchmarks confront this explicitly.

**Build.** Prefer PRs dated after known model training cutoffs; record each model's cutoff beside its score; consider a held-out "fresh" slice.

**Learn/Research.** Data leakage and memorization in code benchmarks; canary/holdout strategies; how leaderboards disclose cutoffs.

**Done-when.** Every task carries a date; every model carries a cutoff; your writeup states the contamination posture plainly.

**Pitfalls.** Pretending contamination is solved. Transparency *is* the credibility here — state limitations openly.

## Step 17 — Flakiness & determinism

**Goal.** Guarantee that a task's outcome depends only on the patch, not on luck.

**Why.** A flaky test makes the *same* patch pass sometimes and fail others — pure noise in your signal.

**Build.** Repeat-run detection during curation; network isolation inside containers; seed control where relevant; quarantine nondeterministic tasks.

**Learn.** Sources of test nondeterminism (time, network, ordering, randomness) and how to neutralize them.

**Done-when.** Each task produces the identical outcome across repeated gold-patch runs.

**Pitfalls.** Network access inside the sandbox reintroducing flakiness (and contamination). Default to offline execution.

## Step 18 — Fairness & reproducibility audit

**Goal.** Prove a stranger can reproduce your numbers.

**Why.** Reproducibility by third parties is the ultimate credibility test — and the thing hiring managers actually poke at.

**Build.** Lock prompt/budget/workspace across all runs; publish exact run instructions; do a clean-room re-run yourself from the published dataset + harness.

**Learn.** What "reproducible eval" demands end to end.

**Done-when.** Following only your public instructions, a from-scratch run reproduces a leaderboard number within variance.

**Pitfalls.** Hidden local state (cached creds, machine-specific config) that makes it work only on your box.

---

# STAGE G — Scale

## Step 19 — Grow the dataset with diversity

**Goal.** Expand from one repo / ~10 tasks to ~5–10 repos / ~30–50 tasks, spread across bug type and difficulty.

**Why.** A score dominated by one project's quirks isn't a language benchmark. Diversity is what makes "TS-Bench" mean *TypeScript*, not "the swr benchmark."

**Build.** Re-run Steps 5–8 across more repos; label tasks by difficulty and category; keep the gold/empty gate on every new instance.

**Learn.** Sampling for representativeness; difficulty labeling.

**Done-when.** Repo/difficulty distribution is documented, and every task still passes the gold/empty gate.

**Pitfalls.** Quality erosion as you scale volume. Never relax curation to hit a task count.

## Step 20 — Parallel execution at scale (your systems showcase)

**Goal.** Run the full matrix (tasks × models × k repeats) fast and reliably.

**Why.** 50 tasks × 5 models × 5 repeats = 1,250 sandboxed jobs — an embarrassingly parallel distributed workload. This is where your backend identity shines: a "systems engineer who built a fast, parallel coding-agent eval" is a sharper story than "another AI hobbyist."

**Build.** A job queue (Kafka) of eval jobs consumed by a worker pool (Kubernetes Jobs), writing results to Postgres; idempotency, retries, dead-lettering, progress monitoring, result aggregation.

**Learn.** Distributed job orchestration for evals: idempotency, at-least-once vs exactly-once, failure isolation, aggregation.

**Done-when.** The full matrix runs unattended, survives worker failures, and aggregates into a consistent result set.

**Pitfalls.** Non-idempotent jobs double-counting on retry; noisy-neighbor resource contention skewing timing-sensitive tasks.

---

# STAGE H — Leaderboard + launch

## Step 21 — Leaderboard site

**Goal.** A public page ranking models by resolved %, with cost, date, and cutoff.

**Why.** This is the shareable surface — but it's a *view* over rigorous data, not the project. Keep it simple.

**Build.** Next.js (deploy on Vercel) reading from Postgres/results; v0 can be a static page generated from a results JSON.

**Learn.** Minimal data-driven frontend; presenting results honestly (show cost + variance, not just rank).

**Done-when.** The site renders live results and is deployed at a public URL.

**Pitfalls.** Letting UI polish consume the time rigor needs. Ugly-but-honest beats pretty-but-unverified.

## Step 22 — Methodology writeup & dataset publish

**Goal.** The document that makes the whole thing legible and reproducible.

**Why.** In eval work, the methodology *is* the contribution. This is what gets cited and what a hiring manager reads.

**Build.** A writeup covering: task construction, the fairness contract, gold/empty gate, contamination posture, pass@k, and step-by-step reproduction. Publish the dataset (versioned) on HuggingFace.

**Learn.** Technical writing for evals; how to present limitations as strengths.

**Done-when.** A competent stranger can reproduce a number using only the writeup + published dataset + harness.

**Pitfalls.** Burying limitations. State them up front — it reads as rigor, not weakness.

## Step 23 — Launch & (optionally) open submissions

**Goal.** Ship it publicly and invite others.

**Why.** The launch is the career payoff — and an open submission path turns a static project into a living one people return to.

**Build.** The launch post (LinkedIn / HN / X): the methodology, the leaderboard, and the *surprising finding* (there's always one). Optionally, a submission process for others to run models/agents against your set.

**Learn.** Framing eval results credibly; handling technical scrutiny in public.

**Done-when.** It's live, reproducible, and someone who isn't you has run against it.

**Pitfalls.** Over-claiming ("the definitive TS benchmark"). Under-claim and let the rigor speak.

---

# STAGE I — Multi-language expansion (v2)

## Step 24 — `PythonAdapter`

**Goal.** Add Python by implementing one adapter — nothing in the core changes.

**Why.** Python is the *easiest* language to add: SWE-bench already solved the hard curation there, so you have massive prior art, reference environments, even existing task sets to extend. Low novelty, high compatibility — a fast, safe first proof that your seam works.

**Build.** `PythonAdapter` (pip/poetry install, pytest run, pytest output parsing); re-run Stages C–F for a couple of Python repos.

**Done-when.** Python tasks flow through the *unchanged* core and pass the gold/empty gate.

**Pitfalls.** Treating it as a rewrite. If the core needs edits to support Python, your Stage-B seam was wrong — fix the seam, not the core.

## Step 25 — `JavaAdapter` (your home turf)

**Goal.** Add Java — the language where *you* have authority most AI-eval people lack.

**Why.** You know Maven/Gradle, JDK versioning, and JVM test frameworks deeply. The catch: Java builds are heavy and slow, so your Docker caching (Step 9) and parallelism (Step 20) matter more here — which again plays to your strengths. "Built a fast, parallel Java coding-agent eval" is a standout line.

**Build.** `JavaAdapter` (Maven/Gradle install, `mvn`/`gradle test`, surefire/JUnit XML parsing — which is actually *cleaner* to parse than JS reporters); re-run Stages C–F for Java repos; lean hard on image caching.

**Learn.** Reproducible JVM builds in containers; JUnit result XML.

**Done-when.** Java tasks flow through the unchanged core; build times are tamed via caching.

**Pitfalls.** Underestimating build time/flakiness in large Java projects. Start with well-tested libraries, not giant frameworks.

## Step 26 — Cross-language leaderboard & second launch

**Goal.** One leaderboard, three languages — and a second wave of attention from the same project.

**Why.** "TS-Bench now covers Java and Python" is a fresh launch moment with no new core work. One project, multiple launches, compounding visibility.

**Build.** Extend the leaderboard to filter/compare by language; publish a combined dataset; write the "going multilingual" post.

**Done-when.** Users can compare model performance across TS / Python / Java on one page, reproducibly.

**Pitfalls.** Cross-language score comparisons implying "model X is better at Java than Python" without controlling for task difficulty. Compare *within* a language unless you've matched difficulty.

---

# Cross-cutting: the skills you'll walk away with

By the end you'll have hands-on depth in the exact stack top AI engineers are hired for:
- **Eval methodology** — fail-to-pass task design, pass@k, contamination, fairness contracts, harness-vs-model isolation.
- **Agent scaffolding** — the observe/act loop, tool use, context management, patch extraction, budgets.
- **LLM infra** — LiteLLM multi-provider orchestration, cost/latency accounting.
- **Reproducible environments** — layered Docker images, deterministic builds, sandbox isolation.
- **Distributed eval at scale** — Kafka/K8s job orchestration applied to AI workloads (your differentiator).
- **Data engineering** — GitHub mining at scale, validation pipelines, versioned datasets.
- **Technical communication** — a methodology writeup others can reproduce.

That combination — *a systems engineer who genuinely understands evals* — is rare and exactly what open-source-first, remote AI companies want.

# Research reading list (revisit as you hit each stage)
- SWE-bench (paper + docs) — the paradigm and the harness. *(Stages A, C, D)*
- SWE-bench Verified — task quality and human validation. *(Stage C)*
- SWE-bench Multilingual — multi-language extension of the core. *(Stages B, I)*
- CLAW-SWE-BENCH — model/harness/task isolation, adapter protocol, fairness contract. *(Stages A, E, F)*
- Terminal-Bench — model-vs-scaffold leaderboard design. *(Stages A, E)*
- mini-swe-agent — the simplest credible reference scaffold. *(Stage E)*
- LiteLLM docs — the model gateway you'll standardize on. *(Stage E)*

# The five-line mental model (never lose this)
1. A **task** = a repo frozen at a buggy commit + a real issue + answer-key tests that fail-before / pass-after.
2. The **agent** sees only the issue + code and produces a patch.
3. The **harness** applies the patch in a sandbox and runs the tests.
4. **Solved** = the target tests pass AND nothing else broke.
5. The **leaderboard** ranks models (or agents) on % solved — run fairly and reported honestly.
