# TS-Bench — A Benchmark & Leaderboard for AI Coding Agents on TypeScript Repos

> Your flagship project reference. Read top to bottom once, then use it as a map while you build.
> The goal isn't to memorize this — it's to understand *why* each piece exists so you can make your own decisions when reality doesn't match the plan.

---

## 0. The one-sentence pitch

**You are building a system that measures how well AI coding agents can resolve real GitHub issues in real TypeScript open-source repositories — objectively, reproducibly, and fairly — and ranks them on a public leaderboard.**

That's it. Everything below is the "how" and, more importantly, the "why."

The question your benchmark answers, in plain English:

> *"If I hand an AI agent a real bug report from a real TypeScript project, how often does it actually produce a fix that passes the project's own tests — without breaking anything else?"*

Nobody has a clean, credible, TypeScript-focused answer to that yet. That gap is your opening.

---

## 1. First principles: what *is* a benchmark, actually?

Strip away the hype. A code-agent benchmark is exactly **four things**. If you understand these four, you understand the entire project.

### 1.1 A dataset of tasks
A frozen collection of problems, each one self-contained and objectively checkable. Not "here are some repos" — each **task** is a precise, reproducible unit (defined in §3).

### 1.2 An execution harness
The machinery that, for each task: builds the exact environment, hands the problem to the agent, collects the agent's answer, and runs it. This is where your systems background is an unfair advantage.

### 1.3 A verifier (scoring)
An **automatic, ungameable** way to decide "did the agent solve it — yes or no." No human judgment. No "looks good to me." A machine-checkable definition of *solved*.

### 1.4 A leaderboard
The public ranking + the writeup. This is the part that travels on LinkedIn and gets you noticed — but it's worthless without the three above being rigorous.

**Why this framing matters:** most people who try to build "an AI benchmark" fail because they treat it as #4 (a nice leaderboard UI) with a hand-wavy #3. The credibility — and the reason serious AI engineers respect this work — lives entirely in #2 and #3. That's also exactly where *you* are strong.

---

## 2. The problem statement (why this, why TypeScript, why now)

### 2.1 The established prior art (study these — they're your blueprint)
- **SWE-bench** (Princeton, Oct 2023) — the canonical one. 2,294 tasks mined from **12 Python repos**. It established the entire "resolve a real GitHub issue, verified by tests" paradigm. Its first RAG baseline scored ~2%; that's how hard real-world code is.
- **SWE-bench Verified** — 500 human-validated tasks; the "clean" subset everyone reports on.
- **SWE-bench Multilingual** — extends the idea beyond Python.
- **Terminal-Bench** (Stanford / Laude Institute) — same philosophy but for terminal tasks; notable because its leaderboard cleanly separates *models* from *agent scaffolds*.
- **CLAW-SWE-BENCH** (2026) — the most relevant recent paper to you. Its core insight: a benchmark score conflates **three** things — (a) the LLM, (b) the *harness/scaffold* that turns the LLM into an agent, and (c) the tasks. Real rigor means deciding which of these you're isolating. Read this one closely; it's basically a design doc for what you're building.

### 2.2 The gap you're filling
SWE-bench is Python-first. The multilingual work exists but TypeScript — arguably the most-used language in the world for real product engineering — has no dominant, well-curated, actively-maintained agent benchmark of its own. TS also has properties that make it *interesting* to benchmark:
- A real **type system** — you can verify not just "tests pass" but "it still typechecks" (`tsc`), a signal Python benchmarks don't have.
- A messier, more diverse **toolchain** (npm/pnpm/yarn, vitest/jest/mocha, esbuild/tsc/swc) — harder to standardize, which is exactly what makes a *good* one valuable and defensible.

### 2.3 Why now
Coding agents are the hottest area in applied AI, and **evals are the highest-status work within it** — the people who build the benchmarks get cited and hired off them. "Another agent" is crowded; "a credible eval for a real language nobody has covered well" is rare.

### 2.4 Your unfair advantage (say this in the LinkedIn post)
You already built a **distributed code-execution platform**. A benchmark harness *is* a sandboxed code-execution-and-verification system running at scale. Most people attempting this burn months building that plumbing. You've built it. So you can skip ahead to the parts that actually signal AI-engineering skill: task design, agent scaffolding, and fair evaluation.

---

## 3. The core data model — anatomy of one task

Everything hinges on this. Get this right and the rest is engineering. This is the SWE-bench schema, which you should adopt (don't reinvent it — compatibility is a feature).

A single **task instance**:

| Field | What it is | Why it exists |
|---|---|---|
| `instance_id` | e.g. `vercel__swr-2891` | Unique, human-readable handle (repo + issue number). |
| `repo` | e.g. `vercel/swr` | Which project. |
| `base_commit` | a commit SHA | The exact state of the repo **where the bug still exists**. Reproducibility anchor. |
| `problem_statement` | the GitHub issue text | The *only* thing the agent is told. This is the task. |
| `gold_patch` | the human fix (diff) | The real PR's code change. **Never shown to the agent.** Used to validate the task and as ground truth. |
| `test_patch` | the test changes from the fixing PR | The "answer key" tests — the tests that prove the fix works. |
| `FAIL_TO_PASS` | list of test names | Tests that **fail at `base_commit`** and **pass after the fix**. The primary success signal. |
| `PASS_TO_PASS` | list of test names | Tests that **already pass** and **must keep passing**. The regression guard. |
| `environment` | node version, package manager, install cmd, test cmd | So the harness can rebuild the exact world. |

### 3.1 Why "fail-to-pass" is the whole trick (first principles)
You need to define "solved" in a way that is **objective, automatic, and un-cheatable**. Human review doesn't scale and isn't reproducible. Here's the reasoning chain:

1. A merged PR that *closes an issue* is, by definition, a real fix that a human accepted.
2. If that PR also **added or changed a test**, then that test encodes "what it means for this bug to be fixed."
3. So: check out the code *before* the fix → that test **fails**. Apply the fix → that test **passes**. That transition (`FAIL → PASS`) is a machine-checkable definition of "the issue is resolved."
4. But an agent could "pass the test" by breaking ten other things. So you *also* keep a set of tests that already passed (`PASS_TO_PASS`) and require they **stay** passing. That's your regression guard.

**Solved = every FAIL_TO_PASS now passes AND every PASS_TO_PASS still passes.** Deterministic. No opinions.

### 3.2 Why `base_commit` + stripping git history (first principles)
This is an **anti-cheating / anti-leakage** measure. If the agent can run `git log` forward or `git pull`, it can just *read the real fix* from history and copy it — you'd be measuring "can it use git," not "can it reason about code." So the harness checks out the exact `base_commit`, then **removes later history and the git remote**. The agent is trapped at the moment the bug exists and must actually solve it.

### 3.3 Why you never show the agent the test_patch or gold_patch
Same reason. The test is the answer. The agent gets the *problem* (issue text) and the *codebase* — nothing else. You apply the test_patch *yourself, after* the agent is done.

---

## 4. The evaluation loop (the beating heart)

For each task, the harness does exactly this:

```
1. BUILD    → spin up a container: repo checked out at base_commit,
              dependencies installed, node pinned. (History/remote stripped.)
2. PROMPT   → give the agent the problem_statement + access to the repo.
3. SOLVE    → the agent explores the code and produces a PATCH (a git diff).
4. SANITIZE → reset any test files the agent touched (it must not weaken the
              tests to "pass"), then apply the agent's patch.
5. INJECT   → apply YOUR test_patch on top (the answer-key tests).
6. RUN      → execute FAIL_TO_PASS and PASS_TO_PASS.
7. SCORE    → resolved = (all FAIL_TO_PASS pass) AND (all PASS_TO_PASS pass).
8. RECORD   → store result + cost + wall-clock + tokens + the agent's patch.
```

Step 4's "reset test files" is subtle and important: without it, a lazy agent could edit the test to always pass. You strip its test edits before injecting the real tests.

### 4.1 Why Docker / containers are non-negotiable (first principles)
Three reasons, all load-bearing:
- **Reproducibility.** Your laptop has node 22 and some global package; a grader's machine has node 18 and different OS libs. The *same* patch could pass on one and fail on the other. A pinned container image freezes the world so a score means the same thing everywhere and forever.
- **Isolation / safety.** You are executing *arbitrary code written by an AI* against real repos. That must never touch your host. (This is precisely what your code-execution platform already handles — reuse it.)
- **Scale + caching.** Layered images let you cache the expensive parts. Adopt SWE-bench's three layers:
  - **Base image** — OS + node + package managers (shared by everything).
  - **Environment image** — one per repo: dependencies installed for that project.
  - **Instance image** — the repo at a specific `base_commit`.
  Build once, reuse across thousands of runs.

---

## 5. The dimension that makes you look *senior*: what are you actually ranking?

This is the CLAW-SWE-BENCH insight, and internalizing it is what separates a toy from a credible benchmark. A raw "resolved rate" mixes together **model × harness × tasks**. You must consciously choose what your leaderboard isolates:

- **Option A — a *model* leaderboard.** Fix ONE reference agent (a simple, fixed scaffold), fix the prompt, fix the token/time budget, then swap only the underlying model (GPT-5.x, Claude, Kimi, MiniMax, Qwen…). The leaderboard ranks *models*. Everything held constant except the model. **Start here** — you control every variable, it's the cleanest science, and it's the easiest to run solo.
- **Option B — an *agent/scaffold* leaderboard.** Fix the model, let people submit their own agent harnesses (like Terminal-Bench does). The leaderboard ranks *scaffolds*. More community-driven, more work to make fair, do it as a v2.

Whichever you pick, the fairness contract is: **same prompt, same runtime/token budget, same workspace rules, same patch-extraction procedure, same verifier.** Write that contract down and put it in your README — that single paragraph is what makes reviewers trust your numbers.

**LiteLLM is your best friend here** — you already know it. It gives you one uniform interface to every provider, so "swap the model" in Option A is a config change, not a rewrite. This is a direct reuse of skills you already have.

---

## 6. Tech stack (with honest reasoning, not just a list)

I'm going to be straight with you where the idiomatic choice differs from your comfort zone, because picking the wrong stack here costs you weeks.

### The data pipeline + harness → **Python**
Not your home turf (you're Java/Spring), but this is the **lingua franca of evals**: SWE-bench, HuggingFace `datasets`, most agent scaffolds, and LiteLLM all live in Python. Fighting that current means reimplementing an ecosystem. Learning it is also itself a resume signal ("built an eval pipeline in the standard tooling"). Key libraries:
- `PyGithub` / GitHub REST + GraphQL API — mining PRs and issues.
- `datasets` (HuggingFace) — packaging and publishing your task set.
- `docker` SDK for Python — driving containers programmatically.
- `litellm` — the multi-provider model gateway (you know this).

### Sandbox / execution → **Docker + your existing code-execution platform**
This is your edge. Your platform's isolation + orchestration layer becomes the runner that executes agent patches and test suites safely and in parallel. Do **not** rebuild this — adapt it.

> **v0.1 note (added after T6):** this reuse happens at the *Docker sandbox upgrade* (Step 9 / Step 20 in the execution plan, "After v0.1" on the task board) — not in the v0.1 harness itself. T6's actual `Sandbox` is a from-scratch, ~15-line, no-isolation `LocalSandbox` (`subprocess.Popen` with a real timeout/kill) built on purpose as a throwaway stand-in, deliberately *not* wired to the code-execution platform yet. That's not a deviation from the plan — the task board's Environment note always scoped v0.1 as "local subprocess runner... Docker becomes a drop-in later." Just don't read this section and expect to find the platform already plugged in; see `claude/ts-bench-task-board.md`'s T6 notes for why.

### Inside the container (the TS toolchain) → learn this cold
- Node, pinned per repo (via `nvm`/`volta` or just the image tag).
- Package managers: `pnpm`, `npm`, `yarn` — you'll need to detect which each repo uses.
- Test runners: `vitest`, `jest`, `mocha` — you must parse their output to know which named tests passed/failed. This parsing is fiddly and is real work.
- `tsc` (typecheck) and `eslint` — optional *extra* verification signals unique to TS.

### Storage → **PostgreSQL** (your comfort zone)
Runs, results, per-task outcomes, model metadata, leaderboard rows. Straightforward relational data. (`pgvector` is *optional* and only if you later want semantic de-duplication of tasks — skip for v1.)

### Scale / orchestration → **your Kafka + Kubernetes skills** (show them off)
Running 50 tasks × 5 models × 5 repeats = 1,250 sandboxed jobs. That's an embarrassingly-parallel distributed workload — a queue of eval jobs (Kafka) consumed by a pool of workers (K8s Jobs) writing results to Postgres. This is a *perfect* place to demonstrate that you're not just an "AI person" but someone who can run evals at scale. Lean into it.

### Leaderboard → **Next.js** (deploy on Vercel), or start dead-simple
v1 can literally be a static page generated from a results JSON. Don't let the UI become the project. Reads from Postgres, shows rank / resolved-% / cost / date.

### Dataset hosting → **HuggingFace Datasets**
The standard place to publish. Publishing there is part of what makes it "real" and citable.

---

## 7. The build plan, in phases (each phase = a real milestone)

Do these **in order**. Each one is independently valuable and de-risks the next. Rough timeboxes assume evenings/weekends.

### Phase 0 — Learn by running the real thing (≈ week 1)
Before you build anything, **run SWE-bench Lite locally** on ~5 instances with a cheap model. Watch one full task flow with your own eyes: container builds → problem handed over → patch produced → tests run → score. Read the SWE-bench and CLAW-SWE-BENCH papers alongside.
*Why first:* you'll understand the harness by *using* it, and you'll copy proven design instead of inventing broken design. Do not skip this.

### Phase 1 — Data pipeline for ONE repo (≈ weeks 2–4)
Pick one clean, well-tested TS repo (candidates: `colinhacks/zod`, `date-fns/date-fns`, `vercel/swr`, `trpc/trpc`, `sindresorhus/*` utilities). Write the miner:
1. Find merged PRs that close an issue **and** modify a test file.
2. For each candidate: check out `base_commit`, install deps, run the PR's new tests → confirm they **fail**. Apply the gold fix → confirm they **pass**.
3. Keep only instances that validate cleanly. Extract `test_patch`, `FAIL_TO_PASS`, `PASS_TO_PASS`, `gold_patch`, environment metadata.
*Goal:* 5–10 rock-solid validated tasks. This small set teaches you the entire loop. **This phase is where most of the real work and value lives** — task curation is the hard, respected part.

### Phase 2 — Execution harness + verifier (≈ weeks 4–6)
Containerize (base → env → instance layers). Implement the eval loop from §4: apply patch, sanitize tests, inject test_patch, run, score. Wire in your code-execution platform as the sandboxed runner.
**Ship the two sanity checks that prove your harness is trustworthy:**
- **Gold patch must resolve** every task (if the *real human fix* doesn't pass your harness, your harness is broken).
- **Empty patch must fail** every task (if doing *nothing* "passes," your task is broken).
This "gold passes / empty fails" gate is what makes your benchmark believable.

### Phase 3 — Reference agent + first scores (≈ weeks 6–8)
Build a minimal agent scaffold (a basic explore→edit→submit loop; study `mini-swe-agent` for the simplest credible design). Route it through LiteLLM. Run 3–4 models over your 5–10 tasks. Congratulations — you now have real numbers.

### Phase 4 — Scale, publish, launch (≈ weeks 8–10)
Grow to ~30–50 tasks across 5–10 repos. Parallelize with your Kafka/K8s setup. Publish the dataset to HuggingFace. Build the leaderboard page. Write the launch post: *"I built an eval for TypeScript coding agents. Here's the methodology, here's what topped it, here's what surprised me."* Include the fairness contract and the gold/empty sanity checks — that's what earns respect.

---

## 8. Where rigor lives (the difference between "credible" and "cringe")

If you cut corners anywhere, cut them *here last*. These are the things reviewers and hiring managers probe:

- **Contamination / data leakage.** If a model was trained on the repo's history, it may have *memorized* the fix. Mitigate by favoring **recent** PRs (dated after known model training cutoffs) and by stating each model's cutoff next to its score. Being transparent about this is itself a credibility signal.
- **Flaky tests.** Some tests pass/fail nondeterministically (timing, network, randomness). Run each candidate test multiple times during curation and **drop the flaky ones**. A flaky task produces meaningless scores.
- **Test tampering.** Always reset the agent's edits to test files before injecting your test_patch (§4, step 4).
- **Solvability guarantee.** Every task must pass the gold/empty gate (§Phase 2).
- **Fairness across runs.** Fixed prompt, fixed token + wall-clock budget, identical workspace contract for every model/agent. Document it.
- **Statistical honesty.** LLMs are stochastic. Run each task **k times** and report `pass@k` (or resolved-rate ± variance), not a single lucky run. One run per task is a red flag to anyone who knows evals.
- **Diversity.** Spread tasks across repos, difficulty, and bug type so the score isn't dominated by one project's quirks.

---

## 9. What you'll learn along the way (the skill payoff)

This project is a forcing function for the exact skill set "top AI engineers" are hired for:
- GitHub mining at scale (API, rate limits, PR/issue graph).
- Docker image layering + reproducible environments.
- The internals of TS test runners and how to parse their machine output.
- **LiteLLM multi-provider orchestration** (deepens what you have).
- **Agent scaffolding** — the ReAct-style explore/act/observe loop, tool use, patch extraction.
- **Eval methodology** — leakage, pass@k, fairness contracts, harness-vs-model isolation.
- Distributed job orchestration for eval workloads (your Kafka/K8s, applied to AI).

That combination — *systems engineer who understands evals* — is genuinely rare and exactly the profile remote-first, open-source AI companies want.

---

## 10. Your first concrete step (do this within a few days)

Don't design. Don't name it yet. Don't build a UI. Do this:

1. `git clone` SWE-bench and run **SWE-bench Lite** on ~5 instances with a cheap model, end to end.
2. Open the harness code and trace one task: container build → problem → patch → test run → score.
3. Read the SWE-bench paper and the CLAW-SWE-BENCH paper.
4. Then pick your **first TypeScript repo** and start Phase 1.

Once you've *seen* one real evaluation happen, everything in this document will click from "concepts" into "things I know how to build." Start there.

---

### Quick reference — the mental model in five lines
1. A **task** = repo @ a buggy commit + an issue + answer-key tests (fail-before, pass-after).
2. The **agent** sees only the issue + code, and produces a patch.
3. The **harness** applies the patch in a sandbox and runs the tests.
4. **Solved** = target tests now pass AND nothing else broke.
5. The **leaderboard** ranks models (or agents) on % solved, run fairly and reported honestly.
