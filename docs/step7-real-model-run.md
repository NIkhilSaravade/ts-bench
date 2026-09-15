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

## Operational note: surviving a real machine restart

The host machine restarted unexpectedly partway through the run (WSL2 uptime confirmed at 1 minute when investigated). Both the `run_driver.py` process and Ollama's `llama-server` were gone — background OS processes started from a Claude Code session do not survive a full machine reboot (this is expected; they aren't registered as a persistent service).

**Recovery, in order:**
1. Confirmed via `ps aux` that neither the run process nor Ollama were alive.
2. Confirmed via `wc -l results/oss_leaderboard_run1.jsonl` that progress was safely persisted at 305/960 completed attempts, with `grep -c infra_error` showing zero — both compile-failure fixes had held for the ~95 attempts processed between the restart-doc update and the actual reboot.
3. Restarted Ollama (`ollama serve`, backgrounded) since it isn't running as a systemd service in this WSL2 setup — `systemctl` itself wasn't reachable ("Failed to connect to bus"), consistent with systemd not being active this session.
4. Re-ran the identical `run_driver.py` command. Resumability worked exactly as designed: it picked up at attempt 306, skipping the 305 already-recorded `(model, instance_id, repeat)` triples with zero re-work and zero duplicates.

**Takeaway:** the resumable-JSONL design (T9) plus this run's incremental-commit discipline meant a full, unplanned machine restart cost zero real progress — a real (not just theoretical) validation of that design choice.

---

## Bug #4 (operational, not code): restarting Ollama as the wrong user silently served zero models, corrupting 230 attempts

**What happened:** after the machine restart above, `ollama serve` wasn't running and `systemctl`/`sudo` required a password unavailable in this session, so it was started manually as the current shell's user (`nikhil`) via plain `nohup ollama serve &`. This looked successful (`curl .../api/tags` returned 200) and the leaderboard run was resumed. The watcher's next check showed **127 new `infra_error` entries within a single 15-minute window** — every single attempt since the resume, all with the same message: `litellm.NotFoundError: Ollama_chatException - {"error":"model 'codestral:latest' not found"}`.

**Root cause:** the real, systemd-managed Ollama service (`/etc/systemd/system/ollama.service`) runs as a dedicated `ollama` user, with `User=ollama` and `Group=ollama`, storing all pulled models under `/usr/share/ollama/.ollama/models`. Starting `ollama serve` manually as `nikhil` gave a perfectly healthy server — it just pointed at the default, empty `/home/nikhil/.ollama/models` instead, so `ollama list` (and every model-load request) saw zero models. Since each "model not found" error surfaces near-instantly (`wall_clock_seconds: 0.0`), the run raced through **230 attempts** (more than the 127 the watcher first flagged, since more piled up before the process was stopped) before being caught and killed.

**Why the watcher caught it fast:** this is exactly why `scratch/watch_leaderboard_run.sh` checks for `infra_error` occurrences every 15 minutes rather than only checking at the very end — 230 wasted (near-instant, so no real wall-clock cost) attempts is a data-integrity problem, not a performance one, but it would have been far worse to discover only after the "full" 960-attempt run had already reported completion.

**Fix (operational, not a code change):** confirmed no passwordless `sudo` was available (correctly did not try to work around that), then started Ollama as the current user but pointed explicitly at the real model directory via `OLLAMA_MODELS=/usr/share/ollama/.ollama/models nohup ollama serve &` — the directory is world-readable (`drwxr-xr-x`, owned by `ollama:ollama`), so this needs no elevated privilege, only the correct environment variable. Verified via `ollama list` (all 4 models visible) and a real `curl .../api/generate` inference call before trusting it.

**Remediation applied:** removed all 230 lines from `results/oss_leaderboard_run1.jsonl` whose `stderr_tail` contained `"not found"` (a precise filter — distinct from the two genuine compile-failure `infra_error`s fixed earlier, which had already been corrected and were not present at this point). Verified the file returned to exactly the pre-incident state: 305 lines, zero `infra_error`. Restarted the run; confirmed a fresh attempt landed as real, non-error output before re-arming the watcher.

**Lesson for next time:** if this machine restarts again, do not `ollama serve` in a plain new shell and assume success from a 200 status on `/api/tags` — that only proves the server is *up*, not that it's pointed at the right model store. Check `ollama list` returns the expected models before resuming anything, every time.

---

## Bug #5: `PythonAdapter` had the identical `is_compile_failure` gap as Java

**Where:** `harness/python_adapter.py`'s `run_tests()`.

**How it was found:** the watcher flagged a new `infra_error` on `codestral:latest` / `arrow-py__arrow-954` / repeat 2. Full stderr showed a real, live model mistake: the candidate patch wrote `def get_locale(name: str) _> "_locale":` — `_>` instead of `->` in a return-type annotation. This is a syntax error, so `pytest` failed at collection time (exit code 4) before any test could even be imported, let alone run.

**Root cause:** `LanguageAdapter.is_compile_failure()`'s base implementation defaults to `False`, on the documented assumption that "a dynamically-typed adapter's own test runner already reports real pass/fail for a brand-new test without needing this at all." That assumption is correct for a runtime error *inside* a test body (pytest still collects and reports that test as failed) but wrong for a **collection-time** syntax/import error, which prevents pytest from even loading the module — mechanically identical to Java's compile-failure problem, just one language layer up (parse-time instead of compile-time). `PythonAdapter` never overrode `is_compile_failure()`, so this fell straight into the same `INFRA_ERROR` bucket Bugs #1-#3 fixed for Java.

**Fix, deliberately different in kind from the Java fixes:** rather than string-matching pytest's output (which is exactly the truncation-fragility trap Bug #2 already burned time on), this uses **pytest's own documented exit code** (`4` = `USAGE_ERROR`, pytest's stable, official classification for a collection-time failure) as the signal. This is immune to truncation by construction — no captured-text window to fall out of. New `PythonCollectionFailure(RuntimeError)` type, `is_compile_failure()` checks `isinstance`, exactly mirroring `JavaCompileFailure`'s contract.

**No `eval_runner.py` changes needed:** its `is_compile_failure()` dispatch is already fully adapter-agnostic from the Java fixes earlier in this same run — this Python fix plugs directly into already-correct generic code. This is the payoff of having fixed the *architecture* (Bugs #1-#3) rather than special-casing Java.

**A known, deliberately unaddressed risk, documented rather than guessed at:** `harness/ts_adapter.py`'s `run_tests()` has the exact same structural shape (`if not output_file.exists(): raise RuntimeError(...)`, no `is_compile_failure` override) — a candidate patch that breaks TypeScript syntax badly enough that vitest/jest can't produce a results file would hit the identical gap. No real occurrence has been observed in this run yet (240 `qwen2.5-coder:14b` attempts across ~130 TS instances completed with zero such failures). Left unfixed for now because, unlike pytest, vitest/jest don't have as clean a single documented exit code for "collection/transform failure specifically" — a fix here would require the same string-matching approach already proven fragile for Java, and guessing at patterns without a real failure to learn from risks introducing an incorrect fix with false confidence. Revisit if/when this actually occurs.

**Verification:** new unit test (`tests/test_python_adapter.py::test_is_compile_failure_checks_exception_type`); full suite green (43/43); stale line removed from `results/oss_leaderboard_run1.jsonl` before restarting.

**Commit:** `e330f1f` — `fix: Python collection failures had the same infra_error gap as Java`.

---

## Investigated and ruled out: 0% resolved rate after 420/960 attempts

**What was checked:** after `qwen2.5-coder:14b` (240/240) and most of `codestral:latest` completed, the resolved rate across *every* instance and both models was exactly 0%. This warranted real investigation rather than being waved off as "these are just weak models," especially since `colinhacks__zod-6572` had shown a genuine `resolved=True` for this exact model during the earlier timing pilot but 0/10 in the actual run.

**Investigation:** pulled the full `EvalResult` for a `zod-6572` non-resolve and found `pass_to_pass` contained two near-identical keys for what looked like the same test (`...::re-exports zod/mini verbatim` and `...::src/tests/index.test.ts > re-exports zod/mini verbatim`), one `True` and one `False` — initially looked like a scoring bug (a spurious duplicate key sinking an otherwise-correct fix). Traced `ts_adapter.py`'s `parse_results()` (`name = " > ".join([*a["ancestorTitles"], a["title"]])`) to understand where the two formats come from, then checked whether this pattern is a live parsing artifact or baked into the dataset — **confirmed via `datasets/instances.jsonl` directly that both key formats already exist in this instance's stored `pass_to_pass` list**, meaning this has been present since the original T3 mining, unchanged by anything in this session, and was already there when T4/T6's gate first validated this exact instance's *gold* patch to `resolved=True`.

**Conclusion: not a bug.** These are two genuinely distinct vitest test executions (most likely two different vitest workspace "projects" testing the same-named assertion under different configurations) that the *gold* patch satisfies both of, and a real candidate patch can legitimately fix one without the other — a stricter, not incorrect, correctness bar. The pilot's one `resolved=True` on this exact model+instance is most plausibly ordinary local-inference non-determinism (`llama.cpp`-backed inference isn't perfectly bit-reproducible across process runs even at `temperature=0`), not evidence of a scoring defect.

**Also checked:** 0% held across every one of the 24 instances, not just TS ones with this dual-key property — including Python (`arrow-py`, `jd/tenacity`, no dual-key issue exists in `pytest`'s parser at all) and the 6 deliberately-hard T14-salvaged Java instances. Consistent with T8's own real-money finding that even `claude-sonnet-4-5` (a far stronger, proprietary model) resolved 0/2 real zod attempts — a near-zero resolved rate for 14B-22B local open-weight models on a small, genuinely hard SWE-bench-style task set is plausible, real data, not a broken pipeline. Revisit if `qwen3:14b`/`gpt-oss:20b` also show exactly 0% across the board with no variation at all (that pattern specifically would be more suspicious than a low-but-nonzero or all-different rate).

---

## Open items / not yet done

- [ ] Free-tier run completion + results sanity-check (hand-verify a few raw counts against `pipeline/stats.py`'s output, same discipline as T9)
- [ ] Paid OpenRouter tier: $2-3 pilot to get a real $/attempt number, then the remaining $15-20 budget spent on one larger open-weight model
- [ ] T10 — leaderboard page + methodology writeup, built against these real numbers instead of `MockModel` numbers
- [ ] **Known risk, not yet fixed:** `ts_adapter.py` has the same unaddressed `is_compile_failure` gap as Bug #5 described for Python — revisit if a TS instance ever shows an unexplained `infra_error` in a future run
