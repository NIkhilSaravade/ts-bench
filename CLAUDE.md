# TS-Bench — instructions for Claude Code in this repo

TS-Bench is a benchmark + leaderboard for AI coding agents on TypeScript/OSS repos. Full context lives in three docs in `docs/`:

- **`docs/ts-agent-benchmark-guide.md`** — the "why": first-principles explanation of what a code-agent benchmark is, the SWE-bench-style task schema, the eval loop, and the overall build plan. Read once for orientation; it doesn't change.
- **`docs/ts-bench-execution-plan.md`** — the detailed, dependency-ordered reference plan (Steps 1–26, Stages A–I). Each step has Goal / Why / Build / Learn / Research / Done-when / Pitfalls. This is the *design* reference; it changes rarely.
- **`docs/ts-bench-task-board.md`** — **the live operating document. Always read this one in full before doing anything.** It reorders the execution plan into small tasks (T1–T15), tracks real status per task, records what was *actually* built (including bugs hit and how they were fixed, real verified numbers, real file names), and has a "Recommended order from here" section for what to do next. This file is more current than the execution plan for "what actually exists in this repo right now" — when the two disagree, trust the task board.

## How to operate in this repo

1. **At the start of every session, read `docs/ts-bench-task-board.md` in full first.** It tells you what's done, what's next, and any accumulated gotchas (environment quirks, library landmines, design decisions already made) that will save you from re-discovering the same bugs a previous session already found and documented.
2. **Work one task at a time**, following the "Recommended order from here" section near the top of the task board, unless the user explicitly asks you to jump to a different task.
3. **Each task's "Build" section is the spec; its "Done-when" gate is the actual finish line.** Never mark a task done, move to the next one, or tell the user something works without actually running the Done-when check and seeing it pass. If a gate fails, that's the finding — fix the real problem, don't route around it or quietly redefine "done."
4. **After finishing a task (or making meaningful progress worth recording), update `docs/ts-bench-task-board.md` yourself, in the same style already used for T1–T9:**
   - Flip that task's row in "The map" table to reflect real status.
   - Add or extend a "Notes from the actual build" section under that task's heading: what was actually built (file/function names), any non-obvious problems hit and exactly how they were fixed, concrete verified numbers/results (not vibes — actual counts, actual test output), and explicit confirmation the Done-when gate passed.
   - The user tracks progress on this project purely by reading this file — it is the deliverable of every session, not just the code. Keep it accurate and current, not aspirational.
   - If something in the task board (a starter prompt, a build note, an assumption) turns out to be stale or wrong once you actually build the thing, correct it in place. This doc reflects ground truth, not the original plan.
5. **Commit after each meaningfully complete unit of work** — code and the corresponding task-board update together in the same commit where that makes sense. Never use `--no-verify` or skip hooks. Never force-push.
6. **Budget discipline — this matters a lot right now:** do not call any paid model API unless the user explicitly says, in the current conversation, that they want to spend real money right now. Default to `mock/*` models (see `agent/loop.py` — `mock/gold`, `mock/empty`, `mock/random:<p>`) or a local Ollama model for all development and testing. The task board's "Recommended order from here" has one specific, explicit step for spending real API budget — don't jump ahead of it on your own initiative.
7. **When stuck, say so plainly** rather than declaring success on a technicality. A Done-when gate that "sort of" passes, or a task marked done with an asterisk, defeats the entire point of this board — the user is trusting it as an accurate record without re-reading your code.

## Environment notes worth knowing before you start

- WSL2 (Ubuntu) on Windows; work inside the Linux filesystem (not `/mnt/c/...`) for performance.
- Python via `uv`; TypeScript repos are mined/tested under `mirrors/`, `instances/`, `scratch/` (all gitignored — never `git add -A` without checking those aren't picked up).
- Full accumulated environment gotchas (pnpm build-script approval, WSL2 IPv6 quirks, LiteLLM provider-string requirements, Corepack env-var traps, etc.) are documented per-task in `docs/ts-bench-task-board.md` — check there before debugging something that smells like it might be a known issue.
