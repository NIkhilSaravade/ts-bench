# LangGraph agentic-workflow track — plan (not yet built)

> Planning document only. Nothing in this file has been implemented. Written for review before any code is written, per the decision to scope this out first. See `docs/ts-bench-task-board.md` and `docs/step7-real-model-run.md` for the state of the main benchmark this sits alongside.

## 1. Goal

`agent/loop.py` (the existing reference agent) is a **deliberately minimal, language-agnostic** scaffold: one plain-text bash command per turn, identical protocol for every model and every language, on purpose — that uniformity is what makes the main leaderboard a fair comparison across models (`docs/fairness_contract.md`). It was never meant to be a *good* agent, just a *fair, fixed* one.

The question this track asks is different: **can a smarter, language-aware agentic workflow — built with LangChain/LangGraph, with real tools instead of a bare shell, and a strategy tailored to each language's failure modes — get a materially better resolved rate out of the exact same free, local Ollama models?** The free-tier run so far (`docs/step7-real-model-run.md`) shows 0% resolved for two fully-completed models under the plain scaffold; this is a legitimate, separate experiment to see whether the scaffold — not the model — was the ceiling.

## 2. Relationship to the existing benchmark — a new track, not a replacement

Per your answer: **`agent/loop.py` stays exactly as it is.** It remains the one and only scaffold used for the main leaderboard (every model in `results/oss_leaderboard_run1.jsonl` and `results/openrouter_haiku_run1.jsonl` keeps meaning what it already means). This is additive:

- New model-string prefix: `langgraph/<underlying-litellm-model>`, e.g. `langgraph/ollama_chat/qwen2.5-coder:14b`. Mirrors the existing `mock/` prefix convention already in `agent/loop.py`.
- New results file: `results/langgraph_track_run1.jsonl` — never mixed into the main leaderboard files, so `pipeline/stats.py` comparisons stay honest (plain-scaffold numbers vs. plain-scaffold numbers only, unless a chart *explicitly* labels the LangGraph track as a separate series).
- Same dataset (`datasets/instances.jsonl`, v0.2), same `harness/eval_runner.py` scoring, same `EvalResult`/`EvalStatus` — this track only replaces *how a patch gets generated*, never how it gets scored. That's what keeps the comparison meaningful: "same task, same scoring, different agent."
- The leaderboard/methodology page (T10, not yet built) would present this as a clearly separate callout — "does a smarter scaffold help?" — not as additional rows in the main model-ranking table.

## 3. Per-language differentiation

Per your answer, both dimensions differ by language, not just the target repo:

- **Language-specific tools** — each graph gets tools shaped for its own ecosystem's real commands, not one generic `run_shell_command` tool.
- **Language-specific prompting/strategy** — different system prompts and step ordering per language, informed by what this session's real debugging already learned about each language's actual failure shapes (documented in `docs/step7-real-model-run.md`'s Bugs #1–#6).

### 3.1 Shared foundation (reused, not reinvented)

The single most important design decision: **the tools are thin wrappers around the already-validated `harness/*_adapter.py` code**, not new test-running logic. Concretely:

- `harness/python_adapter.py`, `harness/java_adapter.py`, `harness/ts_adapter.py` already know the real `install()` and `run_tests()` commands, already handle the real edge cases this session found the hard way (Bug #1–#6: stdout vs stderr, compile-failure classification, the `npx` fix, pytest's exit-code-4 signal, corepack/nvm version pinning, lifecycle-script sanitization). A tool that ran `pnpm test` or `mvn test` directly, from scratch, would silently reintroduce every one of those already-fixed bugs.
- So each language's LangGraph tools call the adapter's own `install()`/`run_tests()` methods (via a small `LocalSandbox`-equivalent already in `harness/local_sandbox.py`), not raw subprocess calls of their own.
- This also means: any *future* adapter bug fix (a Bug #7, say) automatically benefits this track too, with zero duplicate maintenance.

### 3.2 TypeScript graph (`agent/langgraph/ts_graph.py`, planned)

**Tools:**
| Tool | Wraps | Notes |
|---|---|---|
| `read_file(path)` | plain read | shared across all 3 graphs |
| `list_dir(path)` | plain listdir | shared |
| `apply_patch(diff)` / `write_file(path, content)` | plain write + `git diff` for patch extraction | shared, reuses `agent/workspace.py::extract_patch` |
| `install_dependencies()` | `TypeScriptAdapter.install()` | pnpm/npm/yarn auto-detected exactly like the harness does; surfaces the real `ERR_PNPM_IGNORED_BUILDS` retry already built in |
| `run_tests(test_ids=None)` | `TypeScriptAdapter.run_tests()` (post-Bug-#6 fix — direct binary invocation, not `npx`) | returns parsed pass/fail via `parse_results()`, not raw JSON, so the model sees "3 passed, 1 failed: <name>" instead of a results blob |
| `typecheck()` (new, TS-specific) | `tsc --noEmit` if a `tsconfig.json` exists | not currently in the adapter at all — a genuinely new tool, since a real TS type error is a distinct, common failure class this session never had a language-agnostic way to surface early |

**Strategy differences:** TS instances in this dataset are monorepo-shaped (zod, trpc, date-fns) — the prompt should explicitly tell the model to run `install_dependencies()` once, then `typecheck()` before ever running the full test suite (type errors are cheap to catch and expensive to debug from a wall of vitest output). Ordering: read problem → locate relevant file(s) → edit → typecheck → run targeted tests → run full suite → submit.

### 3.3 Java graph (`agent/langgraph/java_graph.py`, planned)

**Tools:**
| Tool | Wraps | Notes |
|---|---|---|
| `read_file` / `list_dir` / `apply_patch` | shared | |
| `install_dependencies()` | `JavaAdapter.install()` | Maven resolve, no test run |
| `compile_check()` (new, Java-specific) | `mvn compile` / `mvn test-compile`, classified via `JavaAdapter._is_compile_failure_text()` | **This directly encodes the single biggest lesson from this session's real debugging**: 6 of this dataset's Java instances are T14-salvaged (the gold patch adds an API the test needs just to *compile*). A model that never checks "does this even compile" before running the full test suite wastes turns on a wall of Maven output it can't parse. Exposing compile-check as its own fast, cheap, separately-callable tool — and telling the model explicitly in its system prompt that some Java tasks require adding new methods/classes just to unblock compilation — targets exactly the failure mode Bugs #1–#3 spent the most effort on. |
| `run_tests(test_ids=None)` | `JavaAdapter.run_tests()` | |

**Strategy differences:** the system prompt for this graph should explicitly explain the "sometimes you must add new API surface, not just fix logic" pattern — information the plain bash-loop agent never gets, since its system prompt is deliberately language-agnostic. Ordering: read problem → locate class(es) → edit → `compile_check()` (loop back to edit on failure, with the compiler's actual error message as feedback) → `run_tests()` → submit.

### 3.4 Python graph (`agent/langgraph/python_graph.py`, planned)

**Tools:**
| Tool | Wraps | Notes |
|---|---|---|
| `read_file` / `list_dir` / `apply_patch` | shared | |
| `install_dependencies()` | `PythonAdapter.install()` | |
| `run_tests(test_ids=None)` | `PythonAdapter.run_tests()` | Bug #5's `PythonCollectionFailure` (pytest exit code 4) surfaces here as a distinct, clearly-labeled "collection error: likely a syntax error in your edit" message, rather than a generic failure — the model gets a much more actionable signal than the plain-loop agent, which only ever sees raw stderr text |

**Strategy differences:** simplest of the three (no compile step, no type-check step) — closest to a standard ReAct loop: read → locate → edit → run targeted `fail_to_pass` tests → run full pass_to_pass suite → submit. The main value-add here is just better tool ergonomics (parsed pass/fail instead of raw pytest text) rather than a fundamentally different strategy.

## 4. Shared state & graph shape

All three graphs share one `AgentState` (LangGraph's typed state dict):

```python
class AgentState(TypedDict):
    instance_id: str
    problem_statement: str
    workspace: Path
    messages: list[BaseMessage]  # LangChain message history
    turns_used: int
    submitted: bool
```

Graph shape (same topology for all three, only the tool set and system prompt differ): a standard LangGraph ReAct-style loop —

```
START -> agent_node (LLM call, decides next tool or submit)
      -> tool_node (executes the chosen tool, appends ToolMessage)
      -> agent_node (loop)
      -> END (on submit, or max_turns / wall_clock exhausted)
```

`langgraph.prebuilt.create_react_agent` (or a small hand-rolled `StateGraph` if the prebuilt one doesn't give enough control over the turn/wall-clock budget) is the natural fit here — it already implements exactly this loop shape.

## 5. Model / tool-calling compatibility — the biggest real risk

This is the one item that could sink the whole plan if not checked early: **LangGraph's tool-calling relies on the underlying model supporting function/tool calls**, unlike `agent/loop.py`'s plain-text protocol, which works with *any* model precisely because it avoids this dependency (see `agent/loop.py`'s own docstring on this exact tradeoff).

- `qwen2.5-coder:14b`, `qwen3:14b`, and `gpt-oss:20b` are all served through Ollama, which does support an OpenAI-style tool-calling API for models that were themselves trained with tool-calling support. Qwen2.5-Coder and Qwen3 both advertise tool-calling support; `gpt-oss` (OpenAI's open-weight release) also supports it. `codestral` is more of an unknown for reliable structured tool-calling — worth an early, cheap smoke test.
- **First real build step should be a tiny standalone smoke test** (one instance, one turn, one tool call) against each of the 4 models *before* building out all three full graphs — if tool-calling reliability turns out to be poor for a given model (a known, common issue with smaller open-weight models — malformed JSON args, hallucinated tool names), that changes the plan (e.g. might need a repair/retry loop around malformed tool calls, or might rule a model out of this track entirely, documented plainly rather than silently worked around).

## 6. New dependencies

`pyproject.toml` currently has no `langchain`/`langgraph` dependency. Would add:
```
"langgraph>=0.2",
"langchain-core>=0.3",
"langchain-ollama>=0.2",   # ChatOllama, native tool-calling support
```
(`langchain-ollama` talks to the same local Ollama server already running — no new service, no new port, no new cost.) Deliberately *not* adding the full `langchain` umbrella package — `langchain-core` + `langchain-ollama` + `langgraph` is enough for a tool-calling ReAct loop, keeping the dependency footprint small and matching this repo's existing "add exactly what's needed" style (see `pipeline/db.py`'s two-line connection helper as precedent).

## 7. Integration point in the driver

`harness/driver.py::run_and_evaluate()` currently does:
```python
agent_result = run_agent(instance, mirrors_dir, model=model, **kwargs)
```
Planned change: a small dispatch, e.g.
```python
if model.startswith("langgraph/"):
    from agent.langgraph.loop import run_agent as run_langgraph_agent

    agent_result = run_langgraph_agent(
        instance, mirrors_dir, model=model.removeprefix("langgraph/"), **kwargs
    )
else:
    agent_result = run_agent(instance, mirrors_dir, model=model, **kwargs)
```
`agent/langgraph/loop.py`'s `run_agent()` would return the *same* `AgentRunResult` dataclass `agent/loop.py` already defines (imported, not redefined) — so `evaluate()`, `EvalResult`, `scripts/run_driver.py`, and `scripts/load_results.py` all work completely unchanged. This is the key seam that keeps this a low-risk addition: everything downstream of "a patch exists" stays exactly as it is today.

The graph dispatch *within* `agent/langgraph/loop.py` (which of the three per-language graphs to build) reads `instance.language` (already a real field on `TaskInstance`, per T13's notes) — not something encoded in the model string.

## 8. Testing / validation plan, before any real Ollama run

Mirrors how every other adapter in this repo was validated — proven small before proven at scale:

1. **Unit-level:** each new tool function tested directly against a real mirror (not mocked), same style as `tests/test_python_adapter.py` etc. — e.g. `install_dependencies()` for TS actually installs a real repo's dependencies.
2. **Single-instance, single-turn smoke test per language + per model** (12 combinations: 3 languages × 4 models) to confirm tool-calling actually works end-to-end before committing to a real multi-turn run. Cheap ($0, local) and fast.
3. **Small pilot**: one real instance per language, full multi-turn loop, one model (`qwen2.5-coder:14b`, since it's the most tool-calling-reliable candidate) — confirm a patch comes out the other end and `evaluate()` scores it without crashing.
4. **Only then**: a real multi-model, multi-instance run, written to `results/langgraph_track_run1.jsonl`, following the exact same resumable-JSONL pattern `scripts/run_driver.py` already uses (no new driver script needed if the model-prefix dispatch above is in place — `run_driver.py` already treats the model string opaquely).

## 9. File/directory layout (planned, not created)

```
agent/
  langgraph/
    __init__.py
    state.py          # shared AgentState TypedDict
    loop.py            # run_agent() entrypoint + language dispatch + budget/turn loop
    tools_common.py    # read_file, list_dir, apply_patch (shared across all 3)
    ts_graph.py        # TS-specific tools + system prompt + graph construction
    java_graph.py       # Java-specific tools + system prompt + graph construction
    python_graph.py     # Python-specific tools + system prompt + graph construction
tests/
  test_langgraph_tools_ts.py
  test_langgraph_tools_java.py
  test_langgraph_tools_python.py
```

## 10. Open questions / risks to resolve during the build, not before

- **Tool-calling reliability on smaller open-weight models** (Section 5) — the one risk worth an early, cheap smoke test rather than a guess.
- **Turn/wall-clock budget parity**: should this track use the same `MAX_TURNS=40` / `WALL_CLOCK_SECONDS=15*60` constants as the plain scaffold, for comparability, or does a tool-calling loop naturally need a different budget shape (e.g. fewer turns since each turn does more)? Leaning toward keeping the same constants for a cleaner "same budget, different scaffold" story, but worth revisiting once real timing data exists.
- **Cost**: still $0 (Ollama only) — this track should probably stay Ollama-only and not be extended to the paid OpenRouter tier without a separate, explicit budget conversation, same discipline as the rest of this session.
- **What "language-specific strategy" looks like concretely for TS's `typecheck()` tool** — genuinely new (no adapter precedent), so its exact command/output-parsing needs to be built and validated fresh, not just wrapped from existing code the way the other tools are.

## 11. Suggested build order

1. Tool-calling smoke test (Section 5) across all 4 Ollama models — go/no-go gate before anything else.
2. `tools_common.py` + `state.py` + one minimal graph (start with Python — simplest, no new tools needed).
3. Python graph pilot run (Section 8, step 3) — prove the whole path end-to-end once.
4. Java graph (adds `compile_check()`) — the highest-value addition given this session's own Java debugging history.
5. TS graph (adds `typecheck()`, the one genuinely new tool) — last, since it's the least precedented.
6. Full pilot run (Section 8, step 4) across all languages × all 4 models, small instance subset first.
7. Update `docs/ts-bench-task-board.md` and `docs/step7-real-model-run.md` with real results, following this session's existing documentation discipline.
