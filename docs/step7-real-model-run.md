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

**Watched continuously** via a background poll script (`scratch/watch_leaderboard_run.sh`, gitignored) checking `results/oss_leaderboard_run1.jsonl`'s line count and any `infra_error` status every 15 minutes — this is what caught bugs #2 and #3 below in near-real-time instead of after the fact.

---

## Bug #2: `is_compile_failure`'s substring check was itself truncation-fragile

**Where:** `harness/java_adapter.py`'s `is_compile_failure()`.

**How it was found:** ~20 minutes into the run, the watcher caught a *second* real `infra_error` — this time on `jhy__jsoup-2602` again, under the exact fix from Bug #1. Investigating the full stored `stderr_tail` showed a real model patch had introduced a syntax error into `HtmlTreeBuilder.java` (a main source file), producing over a hundred repeated `[ERROR] ... class, interface, or enum expected` lines — a genuine cascading-parse-error pattern, but with **no** occurrence of "COMPILATION ERROR" or "Compilation failure" anywhere in the captured text; Maven's own summary banner had been pushed out of the tail entirely by the sheer volume of per-line diagnostics.

**Root cause:** `is_compile_failure()` string-matched against `str(error)` — the *already-truncated* exception message (`stdout[-3000:]` + `stderr[-1000:]`, from Bug #1's fix). This is exactly the truncation-fragility problem T14 originally identified and tried to guard against by checking multiple substrings — but a different cascading error pattern (many short repeated diagnostics rather than one repeated missing-symbol reference) can still push every recognized banner phrase out of a fixed-size tail. Adding one more magic substring to an open-ended allowlist doesn't end this problem, it just delays the next occurrence.

**Fix (structural, not another substring):** introduced `JavaCompileFailure(RuntimeError)`, a distinct exception type. `install()` and `run_tests()` now check Maven's **full, untruncated** `result.stdout` (before any truncation for storage) against a marker list (`_is_compile_failure_text()`) and raise `JavaCompileFailure` specifically when a compile-failure marker is found anywhere in it — truncation for the stored/logged message still happens, but only *after* classification, so it can never affect the classification itself. `is_compile_failure()` now simply checks `isinstance(error, JavaCompileFailure)`. This closes the entire class of bug, not just the two specific error patterns observed so far.

**Verification:** new unit tests (`tests/test_java_adapter.py`) covering both the isinstance-based contract and the specific cascading-error pattern that motivated it; full suite green (41/41 at this point); a direct real-mirror re-check confirmed T14's mining-time salvage path (`pipeline/validate.py`'s `red_run`, via `install()`) still classifies `jhy__jsoup-2602` correctly under the new exception type.

**Commit:** `4938305` — `fix: Java compile-failure detection was still truncation-fragile`.

---

## Bug #3: `install()`'s exception handler in `eval_runner.py` never got the same fix

**Where:** `harness/eval_runner.py`, the `try: adapter.install(sandbox, env)` block.

**How it was found:** immediately after Bug #2's fix, while still investigating the run, a **third** `infra_error` was already sitting in the results file: `stleary__JSON-java-1068`, repeat 1. Its record had `patch_strategy=None` — meaning the failure happened *before* `git.try_apply_patch()` ever ran, i.e. during `install()`, not `run_tests()`.

**Root cause:** Bug #1's fix only added the `is_compile_failure()` check to `run_tests()`'s exception handler. `install()`'s handler was left as a bare `except Exception as e: return done(EvalStatus.INFRA_ERROR, ...)` — an asymmetry that became a real gap the moment `java_adapter.py`'s `install()` was updated (as part of Bug #2's fix) to also raise `JavaCompileFailure`.

**Important nuance investigated before concluding this was "just another instance of the same bug":** `install()` always runs on **bare `base_commit`, before any patch (candidate or test) is applied**. A genuine, persistent compile failure at that stage would mean the dataset instance itself is broken independent of any agent — a real dataset-quality problem, not a scoring bug. This was taken seriously enough to check directly: a fresh, isolated re-run of `install()` against `stleary__JSON-java-1068`'s real `base_commit` (no patches, no other process involved) **succeeded cleanly**. Given several manual diagnostic Maven builds (used to investigate Bug #2) had been run concurrently against the same shared `~/.m2` local repository cache while this background job was still executing, the most likely explanation is transient resource contention between concurrent Maven processes, not a real compile-time defect in the instance. This is recorded as an **operational lesson** rather than a code bug: don't run manual Maven-based diagnostics concurrently with a live Java evaluation run against the same machine's `~/.m2` cache.

**Fix (made regardless of the above, for correctness/symmetry):** mirrored the identical `is_compile_failure()` check onto `install()`'s exception handler. Even though a *real* install()-stage compile failure should be rare to nonexistent for a validated instance, the asymmetry itself was a latent bug — if it ever does fire for real, it must be scored the same honest way, not silently misclassified.

**Verification:** since a real install()-stage compile failure isn't reliably reproducible on demand, added a unit test using a monkeypatched fake `LanguageAdapter` (`tests/test_harness_step10.py::test_evaluate_install_stage_compile_failure_is_resolved_false`) that forces exactly this code path. Full suite green (42/42).

**Remediation applied to the in-flight run:** both bad lines (`jhy__jsoup-2602` rep 0, `stleary__JSON-java-1068` rep 1) were removed from `results/oss_leaderboard_run1.jsonl` before restarting, so `run_driver.py`'s resumability logic retries them under the fixed code instead of treating the wrong classification as permanently done. The run was stopped, the two lines removed, and restarted with the identical command — 210 already-correct completed attempts were preserved and skipped automatically.

**Commit:** `f1871c4` — `fix: install()-stage compile failures had the same infra_error gap`.

---

## Operational lesson: don't run manual Maven diagnostics concurrently with a live Java eval run

Both Bug #2 and Bug #3's investigations involved running one-off diagnostic Python scripts (calling `install()`/`red_run()` directly against real mirrors) *while* the 960-attempt background job was still executing. Since all Maven processes on this machine share one `~/.m2` local repository cache, concurrent builds can plausibly race on partially-written artifacts. No corruption was proven, but it's the most likely explanation for Bug #3's non-reproducing `infra_error`. Going forward: pause or wait between attempts before running ad hoc Maven-based verification while a real run is in flight, or give diagnostic scripts an isolated `-Dmaven.repo.local=`.

---

## Open items / not yet done

- [ ] Free-tier run completion + results sanity-check (hand-verify a few raw counts against `pipeline/stats.py`'s output, same discipline as T9)
- [ ] Paid OpenRouter tier: $2-3 pilot to get a real $/attempt number, then the remaining $15-20 budget spent on one larger open-weight model
- [ ] T10 — leaderboard page + methodology writeup, built against these real numbers instead of `MockModel` numbers
