# TS-Bench Model Leaderboard — Fairness Contract (v0.1)

TS-Bench's primary leaderboard is a **model** leaderboard (Option A, per
CLAW-SWE-BENCH's model/harness/task isolation argument): the scaffold, the
tasks, and the evaluation procedure are held fixed, and only the underlying
model varies. This document is what that fixing means in practice. If any
run in the results table did not follow every clause below, it is not a
valid leaderboard entry — it's a debugging run.

## 1. Scaffold

One reference agent implementation (`agent/`), used unmodified for every
model. Every result row records the git commit SHA of `agent/` at run time.
A scaffold change is a new scaffold version, not a per-model tweak.

## 2. Prompt

The system prompt and per-turn observation template are fixed literal
strings defined in `agent/prompts.py`. No per-model prompt edits, ever —
not even ones that "just" fix a model's known quirk. If a model performs
badly because of a prompting mismatch, that is part of what the score
measures.

## 3. Budget

Enforced identically for every model:
- **Max turns:** 40 agent actions.
- **Wall-clock cap:** 15 minutes per task.

Token counts are deliberately *not* the enforced budget: different
providers tokenize the same text differently, so a fixed token count is
not an equal amount of reasoning room across models. Turns and wall-clock
are budget units that don't depend on tokenizer internals. Cost and token
usage are still logged per run (populated in T8) for transparency, but are
reporting fields, not fairness levers.

## 4. Workspace

Every task starts from the same materialization: the repo at
`base_commit`, history and remote stripped, freshly `git init`'d with one
pristine commit. The agent's only interface to the world is a plain shell
in that workspace — no other tools, no network access. Network isolation
is both a fairness measure (no model can look up external context another
can't) and a contamination control (no model can search for the real fix).

## 5. Patch extraction

The candidate patch is always `git diff` against the workspace's initial
commit, taken when the agent signals it is done or when the budget is
exhausted — whichever happens first. No other patch format is accepted.
A patch that fails to apply is scored unresolved by the harness, never
treated as a scaffold-level error.

## Out of scope for this contract

Which model produces the patch, how many times a task is repeated
(`pass@k`, Step 15), and how the harness scores a submitted patch
(`harness/eval_runner.py::evaluate`) are governed elsewhere and are exactly
the things this contract exists to isolate.
