"""The reference agent scaffold: a minimal explore -> edit -> submit loop,
modeled on mini-swe-agent. One action per turn -- the model outputs a
single bash command, the environment executes it and reports back -- until
the model submits or the turn/wall-clock budget (docs/fairness_contract.md
clause 3) runs out.

Deliberately not using any provider's function/tool-calling API: a plain
text protocol means the exact same request shape works against every model
LiteLLM can reach -- hosted (OpenRouter) or local (Ollama). That's what
keeps this a fair fixed instrument across models (fairness_contract.md
clause 1), not just a simplicity preference.

Two scaffold-level rules exist beyond plain command execution, both applied
identically to every model so neither compromises clause 1:

1. The submit command is only honored if the workspace actually has a
   non-empty `git diff` at that point. Otherwise a model can emit the
   submit command on turn 1 with zero exploration and zero changes,
   producing an empty patch that can never resolve anything -- a non-
   attempt rather than a genuine (even if wrong) fix attempt.

2. Repeat-command handling. We run with temperature=0 (greedy decoding)
   for reproducibility -- see below -- but greedy decoding is a pure
   function of its input: identical conversation history in means
   identical prediction out. If the model's own history becomes periodic
   (e.g. it runs the same exploration command, gets rejected on submit,
   and the resulting prefix looks the same as before), it can fall into an
   exact repeating cycle and never break out on its own. A static text
   nudge cannot reliably break a deterministic cycle once formed -- the
   nudge itself just becomes one more fixed token sequence folded into the
   repeating prefix, so the model regenerates the same completion around
   it every time. So: the first repeat of a command gets a nudge appended
   to its observation, on the chance the model notices and changes course.
   If the same command repeats a 3rd time in a row, we stop trying to
   rescue the run and end it there (submitted=False) rather than burn the
   rest of the turn/wall-clock budget on a run that's provably stuck. A
   run that ends this way is distinguishable after the fact from one that
   genuinely exhausted its budget: turns_used will be less than max_turns
   and submitted will be False.

Known v0.1 gap: this runs commands via plain subprocess with no OS-level
network isolation, same as harness/eval_runner.py's LocalSandbox. The
fairness contract's "no network" workspace clause is a stated policy here,
not yet an enforced one -- real isolation lands with the Docker sandbox
upgrade (task board, "After v0.1").
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import litellm

from agent.prompts import SUBMIT_COMMAND, SYSTEM_PROMPT
from agent.workspace import agent_workspace, extract_patch
from pipeline.schema import TaskInstance

MAX_TURNS = 40  # docs/fairness_contract.md clause 3
WALL_CLOCK_SECONDS = 15 * 60  # docs/fairness_contract.md clause 3
COMMAND_TIMEOUT_SECONDS = 60  # one hung command must not eat the whole budget
OUTPUT_TRUNCATE_CHARS = 4000  # the model doesn't need 50k lines of test output to act
STUCK_REPEAT_LIMIT = 3  # end the run once a command has repeated this many times in a row
MAX_RATE_LIMIT_RETRIES = 3  # bounded, narrow retry -- only for a 429, never retry-on-anything
RATE_LIMIT_BACKOFF_SECONDS = 5  # doubles each attempt: 5s, 10s, 20s

CODE_BLOCK_RE = re.compile(r"```(?:bash|sh)?\s*\n(.*?)```", re.DOTALL)

REPEAT_COMMAND_NUDGE = (
    "\n\nNOTE: this is the exact same command you ran previously, and it will "
    "produce the exact same output again -- repeating it will not help. If it "
    "returned matches, open one of those files directly (for example "
    "`sed -n '1,80p' <file>` or `cat -n <file>`) and read the surrounding code. "
    "If you're unsure what to do next, try a different exploration command or "
    "make an edit."
)


class MissingAPIKeyError(RuntimeError):
    pass


@dataclass
class AgentRunResult:
    patch: str
    turns_used: int
    submitted: bool  # True = model emitted the submit command; False = budget ran out or run got stuck
    wall_clock_seconds: float
    tokens_used: int = 0  # sum of total_tokens across every completion call this run made
    # sum of litellm.completion_cost() across every call; 0.0 if litellm has no
    # pricing data for the model (e.g. local Ollama)
    cost_usd: float = 0.0
    transcript: list[dict] = field(default_factory=list)  # for debugging / later logging


def run_agent(
    instance: TaskInstance,
    mirrors_dir: Path,
    model: str,
    max_turns: int = MAX_TURNS,
    wall_clock_seconds: float = WALL_CLOCK_SECONDS,
) -> AgentRunResult:
    api_key = _resolve_api_key(model)
    start = time.monotonic()

    with agent_workspace(instance, mirrors_dir) as workspace:
        if model.startswith("mock/"):
            return _run_mock_agent(model, instance, workspace, start)

        messages = [
            {
                "role": "user",
                "content": SYSTEM_PROMPT.format(
                    problem_statement=instance.problem_statement,
                    submit_command=SUBMIT_COMMAND,
                ),
            }
        ]

        turns_used = 0
        submitted = False
        last_command: str | None = None
        repeat_count = 0
        tokens_used = 0
        cost_usd = 0.0

        for turn in range(1, max_turns + 1):
            if time.monotonic() - start >= wall_clock_seconds:
                break

            completion_kwargs = dict(
                model=model,
                messages=messages,
                temperature=0,  # as deterministic as the provider allows -- a fixed instrument, not the star
                timeout=120,
                max_tokens=1024,  # cap output -- prevents 64k-token default from blowing past the timeout
                # we retry ourselves, narrowly -- litellm's own blind retries hid a hang behind
                # a wall of repeated "Provider List" log lines
                num_retries=0,
            )
            if api_key is not None:
                completion_kwargs["api_key"] = api_key

            response = _complete_with_rate_limit_retry(completion_kwargs)
            tokens_used += _extract_total_tokens(response)
            cost_usd += _safe_completion_cost(response)
            reply_text = response.choices[0].message.content or ""
            messages.append({"role": "assistant", "content": reply_text or "(no output)"})
            turns_used = turn

            command = _extract_command(reply_text)
            if command is None:
                messages.append(
                    _observation(
                        "No bash code block found in your last response. "
                        "Respond with exactly one ```bash ... ``` block.",
                        turn,
                        max_turns,
                    )
                )
                continue

            if command.strip() == SUBMIT_COMMAND:
                if extract_patch(workspace).strip():
                    submitted = True
                    break
                messages.append(
                    _observation(
                        "You ran the submit command, but the repository has no "
                        "changes yet (`git diff` is empty). Explore the relevant "
                        "files and make the fix before submitting.",
                        turn,
                        max_turns,
                    )
                )
                continue

            stdout, stderr, exit_code = _run_command(workspace, command)

            if command.strip() == last_command:
                repeat_count += 1
            else:
                repeat_count = 1
            last_command = command.strip()

            body = (
                f"Command: {command}\nExit code: {exit_code}\n"
                f"Stdout:\n{_truncate(stdout)}\nStderr:\n{_truncate(stderr)}"
            )
            if repeat_count >= 2:
                body += REPEAT_COMMAND_NUDGE
            messages.append(_observation(body, turn, max_turns))

            if repeat_count >= STUCK_REPEAT_LIMIT:
                break

        patch = extract_patch(workspace)

    return AgentRunResult(
        patch=patch,
        turns_used=turns_used,
        submitted=submitted,
        wall_clock_seconds=time.monotonic() - start,
        tokens_used=tokens_used,
        cost_usd=cost_usd,
        transcript=messages,
    )


def _complete_with_rate_limit_retry(completion_kwargs: dict):
    """Retry ONLY on a provider-reported rate limit, narrowly and with backoff.

    litellm's own built-in retries were disabled (num_retries=0 above) because
    they retried blindly on any failure -- including a genuine hang -- hiding
    it behind a long stream of repeated log lines instead of surfacing a real
    error fast. A 429 is different: it's a known, transient, well-identified
    condition worth waiting out a bounded number of times before giving up.
    """
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            return litellm.completion(**completion_kwargs)
        except litellm.exceptions.RateLimitError:
            if attempt == MAX_RATE_LIMIT_RETRIES:
                raise
            time.sleep(RATE_LIMIT_BACKOFF_SECONDS * (2**attempt))


def _run_mock_agent(model: str, instance: TaskInstance, workspace: Path, start: float) -> AgentRunResult:
    """MockModel: exercises the full agent -> patch -> evaluate() pipeline with
    zero network calls and zero cost, so the harness can be proven end-to-end
    before spending anything (T8 goal). Two variants:

    - "mock/gold": applies the task's own gold_patch and submits -- should
      resolve every FAIL_TO_PASS test when scored, proving the happy path.
    - "mock/empty": makes no changes and never submits -- a deterministic
      "clean fail, no attempt" baseline, proving the harness scores a non-
      attempt as unresolved without crashing.
    """
    variant = model.removeprefix("mock/")
    transcript = [{"role": "system", "content": f"[MockModel variant={variant!r}, no LLM calls made]"}]

    if variant == "gold":
        result = subprocess.run(
            ["patch", "-p1", "--fuzz=0"],
            input=instance.gold_patch,
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"mock/gold could not apply {instance.instance_id}'s gold_patch: {result.stderr}"
            )
        submitted = True
        turns_used = 1
    elif variant == "empty":
        submitted = False
        turns_used = 0
    else:
        raise ValueError(f"unknown mock model variant {variant!r} (expected 'mock/gold' or 'mock/empty')")

    return AgentRunResult(
        patch=extract_patch(workspace),
        turns_used=turns_used,
        submitted=submitted,
        wall_clock_seconds=time.monotonic() - start,
        tokens_used=0,
        cost_usd=0.0,
        transcript=transcript,
    )


def _extract_total_tokens(response) -> int:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0
    return getattr(usage, "total_tokens", 0) or 0


def _safe_completion_cost(response) -> float:
    # litellm has no pricing table for every model (local Ollama models, for
    # instance) -- when it doesn't, this raises. Cost tracking is a nice-to-
    # have on top of tokens_used, never worth crashing a run over.
    try:
        return litellm.completion_cost(response) or 0.0
    except Exception:
        return 0.0


def _resolve_api_key(model: str) -> str | None:
    # Only OpenRouter needs a key here. Local providers like ollama_chat/
    # talk to a server on localhost and need none -- that's the whole
    # appeal, so don't force the OpenRouter check on them.
    if not model.startswith("openrouter/"):
        return None

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise MissingAPIKeyError(
            "OPENROUTER_API_KEY is not set. Get a real key from "
            "https://openrouter.ai/keys, then:\n"
            "  export OPENROUTER_API_KEY=<the actual key>\n"
            "before running this again."
        )
    return key


def _extract_command(reply_text: str) -> str | None:
    matches = CODE_BLOCK_RE.findall(reply_text)
    if not matches:
        return None
    return matches[-1].strip()  # only the LAST block counts, matching the system prompt's stated rule


def _run_command(workspace: Path, command: str) -> tuple[str, str, int]:
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"[command timed out after {COMMAND_TIMEOUT_SECONDS}s]", -1


def _truncate(text: str) -> str:
    if len(text) <= OUTPUT_TRUNCATE_CHARS:
        return text
    half = OUTPUT_TRUNCATE_CHARS // 2
    return text[:half] + "\n...[truncated]...\n" + text[-half:]


def _observation(body: str, turn: int, max_turns: int) -> dict:
    return {"role": "user", "content": f"{body}\n\n[Turn {turn} of {max_turns}]"}
