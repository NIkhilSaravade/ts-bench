"""Step 15 / T9: turn a repeats-JSONL of individual EvalResults into resolved
%, pass@k, variance, and total cost per model.

pass@k derivation (Chen et al. 2021 / Codex / HumanEval): for one task, draw
n independent samples, c of which resolve it. The estimator answers "if I'd
only budgeted k attempts instead of n, and those k were a uniformly random
subset of the n I actually drew, what's the probability at least one
resolves?" -- computed exactly from (n, c, k) via a hypergeometric argument,
no re-running required:

    P(a random k-subset has zero successes) = C(n-c, k) / C(n, k)
    pass@k = 1 - C(n-c, k) / C(n, k)

Expanded as a product of ratios (not factorials) to avoid overflow:

    C(n-c, k) / C(n, k) = prod_{i=0}^{k-1} (n-c-i) / (n-i)

Variance: c is itself random from batch to batch, and pass@k is a nonlinear
function of c, so there's no clean closed form for how much pass@k would
wobble on a fresh n-sample batch. Bootstrap instead: resample n outcomes
WITH replacement B times, recompute pass@k on each resample's c', and take
the std dev of that distribution.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field


def pass_at_k(n: int, c: int, k: int) -> float:
    """Exact pass@k estimator given n samples, c of which resolved."""
    if k > n:
        raise ValueError(f"k ({k}) cannot exceed n ({n}) -- only n samples exist to draw from")
    if n - c < k:
        # Fewer failures than k -- a k-subset can't possibly avoid every
        # success, so P(zero successes) = 0 exactly, pass@k = 1 exactly.
        return 1.0
    prob_all_fail = 1.0
    for i in range(k):
        prob_all_fail *= (n - c - i) / (n - i)
    return 1.0 - prob_all_fail


def bootstrap_pass_at_k(
    outcomes: list[bool], k: int, n_bootstrap: int = 1000, seed: int | None = None
) -> tuple[float, float]:
    """Bootstrap the sampling distribution of pass@k for one task's outcomes.

    Returns (bootstrap_mean, bootstrap_std). The std is the number worth
    reporting as "how much would this task's pass@k wobble on a fresh
    n-sample batch."
    """
    n = len(outcomes)
    if n == 0:
        return 0.0, 0.0
    rng = random.Random(seed)
    values = []
    for _ in range(n_bootstrap):
        c_resampled = sum(rng.choice(outcomes) for _ in range(n))
        values.append(pass_at_k(n, c_resampled, k))
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return mean, variance**0.5


@dataclass
class TaskStats:
    instance_id: str
    n: int
    c: int
    resolved_rate: float
    pass_at_k: float  # nan if n < k (not enough repeats yet to estimate this task)
    pass_at_k_bootstrap_std: float


@dataclass
class ModelStats:
    model: str
    k: int
    num_tasks: int
    total_attempts: int
    total_resolved: int
    resolved_rate: float
    resolved_rate_stderr: float  # binomial SE: sqrt(p(1-p)/N) over all attempts, all tasks
    mean_pass_at_k: float  # mean of per-task pass@k, over tasks with n >= k
    mean_pass_at_k_stderr: float  # SE of that mean: sample_std(per-task pass@k) / sqrt(num_tasks)
    total_cost_usd: float
    per_task: list[TaskStats] = field(default_factory=list)


def compute_model_stats(
    records: list[dict], model: str, k: int, n_bootstrap: int = 1000, seed: int | None = None
) -> ModelStats:
    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if r["model"] == model:
            by_task[r["instance_id"]].append(r)

    per_task: list[TaskStats] = []
    total_attempts = 0
    total_resolved = 0
    total_cost = 0.0
    pass_at_k_values: list[float] = []

    for instance_id, rows in sorted(by_task.items()):
        outcomes = [bool(r["resolved"]) for r in rows]
        n = len(outcomes)
        c = sum(outcomes)
        total_attempts += n
        total_resolved += c
        total_cost += sum(r.get("cost_usd") or 0.0 for r in rows)

        if n >= k:
            p_at_k = pass_at_k(n, c, k)
            _, boot_std = bootstrap_pass_at_k(outcomes, k, n_bootstrap, seed)
            pass_at_k_values.append(p_at_k)
        else:
            p_at_k = float("nan")
            boot_std = float("nan")

        per_task.append(
            TaskStats(
                instance_id=instance_id,
                n=n,
                c=c,
                resolved_rate=c / n if n else 0.0,
                pass_at_k=p_at_k,
                pass_at_k_bootstrap_std=boot_std,
            )
        )

    resolved_rate = total_resolved / total_attempts if total_attempts else 0.0
    resolved_rate_stderr = (
        (resolved_rate * (1 - resolved_rate) / total_attempts) ** 0.5 if total_attempts else 0.0
    )

    if pass_at_k_values:
        mean_pass_at_k = sum(pass_at_k_values) / len(pass_at_k_values)
    else:
        mean_pass_at_k = float("nan")

    if len(pass_at_k_values) > 1:
        sample_var = sum((v - mean_pass_at_k) ** 2 for v in pass_at_k_values) / (len(pass_at_k_values) - 1)
        mean_pass_at_k_stderr = (sample_var / len(pass_at_k_values)) ** 0.5
    else:
        mean_pass_at_k_stderr = float("nan")

    return ModelStats(
        model=model,
        k=k,
        num_tasks=len(by_task),
        total_attempts=total_attempts,
        total_resolved=total_resolved,
        resolved_rate=resolved_rate,
        resolved_rate_stderr=resolved_rate_stderr,
        mean_pass_at_k=mean_pass_at_k,
        mean_pass_at_k_stderr=mean_pass_at_k_stderr,
        total_cost_usd=total_cost,
        per_task=per_task,
    )
