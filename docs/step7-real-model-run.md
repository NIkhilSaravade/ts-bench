# Step 7 — Real-model leaderboard run: findings log

> Live document. Every bug found, decision made, and result produced while running real models (free-tier local Ollama models, then a small paid OpenRouter tier) through TS-Bench for the first time. Updated as the work happens, not written up after the fact — see `docs/ts-bench-task-board.md` for the per-task build history this continues from (T1–T15 are all done; this is "step 7" of that board's "Recommended order from here").

## Why this document exists

Every prior task (T1–T15) was proven against `mock/*` models or, for a handful of smoke-test calls, against paid Anthropic models under tight budget. This is the first time *real, imperfect model output* — not a gold patch, not a mock coin flip — flows all the way through the full pipeline at scale. That's exactly the condition under which latent bugs surface: gates before this only ever exercised the gold patch (which always compiles, always applies cleanly) or an empty patch (a clean, uninteresting failure). A real model's patch is neither, and this section exists to catch and document, in detail, whatever gets caught out by that.

---

## Hardware and model selection

**Machine:** Intel i7-14700K, 32GB RAM, RTX 5060 Ti (16GB VRAM), Ollama running locally on WSL2.

**Free tier (this document's main subject): 4 already-pulled open-weight models, spanning 3 labs:**
| Model | Size (quantized) | Lab | Notes |
|---|---|---|---|
| `qwen2.5-coder:14b` | 9.0GB | Alibaba/Qwen | Already validated against the scaffold in T7 (real zod runs, see task board) |
| `codestral:latest` | 12GB | Mistral | Code-specialized |
| `qwen3:14b` | 9.3GB | Alibaba/Qwen | General-purpose, not code-specialized — a deliberate "coder vs. general" comparison point against `qwen2.5-coder:14b` |
| `gpt-oss:20b` | 13GB | OpenAI | OpenAI's open-weight release — a genuinely notable name for a leaderboard |

All four fit individually within 16GB VRAM. Chosen over pulling new models because they already span real lab/specialization diversity — a richer comparison than 3 near-duplicate Qwen coder sizes would have been.

**Paid tier (OpenRouter, $15-20 budget): deferred until after this free-tier run lands** — plan is one larger open-weight model (likely `qwen2.5-coder:32b`, same family as the local 14B, for a direct "does more parameters help" story), preceded by a small ($2-3) pilot to get a real $/attempt number before committing the rest of the budget. Not started yet as of this document's first entry.

---

## Timing pilot (before committing to the full matrix)

Ran single real attempts against `ollama_chat/qwen2.5-coder:14b` across all three languages to estimate wall-clock budget for the full 4-model × 24-instance × 10-repeat (960-attempt) matrix before committing to it:

| Instance | Language | Wall clock | Notes |
|---|---|---|---|
| `colinhacks__zod-6530` | TypeScript | ~73s (cold) | First-ever call in the session — includes Ollama loading the model into VRAM |
| `colinhacks__zod-6587` | TypeScript | ~73s avg (combined w/ above) | |
| `colinhacks__zod-6572` | TypeScript | 39s (warm) | **Genuinely resolved=True** — a real, non-mock solve, matching T7's finding that Haiku also solved this instance |
| `arrow-py__arrow-954` | Python | 17.7s (warm) | |
| `jhy__jsoup-2602` | Java | 6.4–7.5s | Fast because it fails to compile almost immediately (see bug below) — not representative of a case that reaches a full Surefire run |

**Estimate:** blending ~40-70s (TS), ~18s (Python), ~7s+ (Java, likely higher for instances that do compile) gives a rough average of ~40-45s/attempt. At 960 total attempts: **~10-12 hours**, run once, in the background, fully resumable.

---

## Bug #1 (found during the timing pilot): real Java compile failures were mis-scored as `infra_error`

**Where:** `harness/eval_runner.py`, the `run_tests()` exception handler; secondarily `harness/java_adapter.py`'s `run_tests()` error message.

**How it was found:** the Java timing pilot (`jhy__jsoup-2602` via `qwen2.5-coder:14b`) came back `status=infra_error` in 6.4 seconds — suspiciously fast for a real Maven build, and a status that would silently exclude the attempt from scoring entirely rather than counting it as a fail.

**Root cause, in two layers:**
1. `java_adapter.py`'s `run_tests()` raised its "no JUnit XML report produced" `RuntimeError` using only `result.stderr` — but Maven's own `[ERROR]` diagnostics (including `COMPILATION ERROR`) go to **stdout**, not stderr. This is the *exact same bug* T14 already found and fixed for `install()` (see task board T14 notes), but the fix was never mirrored onto `run_tests()`. The result: the error message was empty/useless, hiding the real cause.
2. Once stdout was included, the real cause was visible: `jhy__jsoup-2602` is one of T14's own "salvaged" instances (see task board T14 notes on "compile failure as a valid fails-at-base signal") — its gold patch adds a method, `HtmlTreeBuilder.insertNode()`, that the injected test needs just to **compile**. An empty (or any incomplete) candidate patch obviously doesn't add that method, so Maven's test-compile phase fails before Surefire ever runs a single test. **This is a completely legitimate "the agent didn't solve it" outcome** — but `eval_runner.py` classified *any* exception out of `run_tests()`, compile failures included, as `EvalStatus.INFRA_ERROR`.

**Why this matters, concretely:** `INFRA_ERROR` results are excluded from the resolved/unresolved denominator (that's the whole point of the status — distinguishing "the model failed" from "our infrastructure failed," a distinction T8 built specifically so a billing error never deflates a model's score). But a compile failure caused by the *model's own incomplete patch* is not an infra problem — it's a real failure that belongs in the denominator. Left unfixed, **every model's Java resolved-rate on any T14-salvaged instance would have been silently inflated** (the hardest, most honest failures excluded from scoring rather than counted against the model) — exactly the kind of methodology gap that would not survive scrutiny in an interview.

**Why it was never caught before:** every previous Java gate (T14's own validation, the gold/empty gate) only ever ran the *gold* patch through this path, and the gold patch by definition adds the missing API, so it always compiles. This is the first time a real, imperfect patch has gone through `JavaAdapter.run_tests()` at all.

**Fix:**
- `java_adapter.py`: `run_tests()`'s error message now includes `stdout` (last 3000 chars) alongside `stderr`, mirroring `install()`'s existing fix.
- `eval_runner.py`: the `run_tests()` exception handler now checks `adapter.is_compile_failure(e)` (the same hook T14 built for mining-time salvage, exposed on every `LanguageAdapter`, defaulting to `False` for TS/Python). If it's a compile failure, the result is `EvalStatus.OK, resolved=False`, with every `fail_to_pass`/`pass_to_pass` target explicitly marked `False` (didn't pass — because it never ran) rather than being dropped from the record. Only a genuine non-compile exception (JDK missing, timeout, OOM, etc.) still falls through to `INFRA_ERROR`.

**Verification:**
- New test: `tests/test_harness_step10.py::test_evaluate_compile_failure_is_resolved_false_not_infra_error` — a real integration test (not mocked) that runs an empty patch against the real `jhy__jsoup-2602` mirror and asserts `status == OK, resolved is False`, every `fail_to_pass_results` value `False`.
- Full suite re-run after the fix: `uv run ruff check .` clean, `uv run pytest -q` → 40/40 passing.
- Re-ran the exact same pilot attempt (`qwen2.5-coder:14b` vs. `jhy__jsoup-2602`) after the fix: now correctly reports `status=ok resolved=False` instead of `status=infra_error`.

**Commit:** `8b0b60e` — `fix: real-agent Java compile failures were mis-scored as infra_error`.

---

## The full free-tier run

**Launched:** background job, `scripts/run_driver.py --models ollama_chat/qwen2.5-coder:14b,ollama_chat/codestral:latest,ollama_chat/qwen3:14b,ollama_chat/gpt-oss:20b --instances all --repeats 10 --out results/oss_leaderboard_run1.jsonl`.

**Scope:** 4 models × 24 instances (13 TS + 5 Python + 6 Java) × 10 repeats = 960 real, non-mock attempts. Zero cost (local inference only). Resumable: `run_driver.py`'s existing `(model, instance_id, repeat)` skip logic (T9) means an interruption just requires re-running the identical command.

**Verified actually running, not just launched:** `ps aux` showed `ollama`'s `llama-server` subprocess at 334% CPU / 54% memory — genuinely computing, not stalled — a few minutes after launch.

*(This section will be updated with real results, any further bugs found, and final per-model numbers once the run completes.)*

---

## Open items / not yet done

- [ ] Free-tier run completion + results sanity-check (hand-verify a few raw counts against `pipeline/stats.py`'s output, same discipline as T9)
- [ ] Paid OpenRouter tier: $2-3 pilot to get a real $/attempt number, then the remaining $15-20 budget spent on one larger open-weight model
- [ ] T10 — leaderboard page + methodology writeup, built against these real numbers instead of `MockModel` numbers
