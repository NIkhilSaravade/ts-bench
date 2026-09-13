from agent.loop import run_agent
from harness.eval_result import EvalResult, EvalStatus
from harness.eval_runner import evaluate


def run_and_evaluate(model, instance, mirrors_dir, wall_clock_seconds=None):
    """Run `model` on `instance` and evaluate the resulting patch.

    Anything that goes wrong before a patch exists (rate limits exhausted,
    network error, agent crash, etc.) is reported as EvalStatus.INFRA_ERROR
    without ever touching the harness. Anything that goes wrong after a
    patch exists (bad apply, timeout, docker/install crash) is already
    classified correctly by evaluate() itself.
    """
    kwargs = {}
    if wall_clock_seconds is not None:
        kwargs["wall_clock_seconds"] = wall_clock_seconds

    try:
        agent_result = run_agent(instance, mirrors_dir, model=model, **kwargs)
    except Exception as e:
        return EvalResult(
            instance_id=instance.instance_id,
            status=EvalStatus.INFRA_ERROR,
            stderr_tail=str(e)[-2000:],
        )

    eval_result = evaluate(instance, agent_result.patch, mirrors_dir)
    eval_result.cost_usd = agent_result.cost_usd
    eval_result.tokens_used = agent_result.tokens_used
    return eval_result
