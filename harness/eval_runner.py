"""The eval runner: Step 10. Orchestrates one (task, candidate_patch) pair
through the full 7-step loop and produces a scored, structured result.

No real agent exists yet (that's T7) -- candidate_patch is handed in directly
so this loop can be proven correct with the gold patch (must resolve every
instance) and an empty patch (must resolve none) before anything untrusted
ever touches it.
"""

import shutil
import tempfile
import time
from pathlib import Path

from harness.adapters import get_adapter
from harness.eval_result import EvalResult, EvalStatus
from harness.local_sandbox import LocalSandbox
from harness.test_outcomes import resolve_test_outcome
from pipeline import gitplumbing as git
from pipeline.schema import TaskInstance


def evaluate(
    instance: TaskInstance,
    candidate_patch: str,
    mirrors_dir: Path,
    install_timeout: int = 600,
    test_timeout: int = 180,
    sandbox: object | None = None,
) -> EvalResult:
    start = time.monotonic()
    mirror = mirrors_dir / f"{instance.repo.replace('/', '__')}.git"

    # mkdtemp() already CREATES the directory it returns -- but
    # materialize_instance refuses to run if its dest already exists (a
    # deliberate safety check from validate.py's use case). So we get a
    # unique parent from mkdtemp, then materialize into a not-yet-existing
    # subdirectory of it.
    #
    # Deliberately NOT embedding instance.instance_id in the prefix (found
    # during T12's Docker testing, but it's a pre-existing risk equally real
    # under LocalSandbox): some workspace packages' postinstall scripts
    # (e.g. one of trpc's examples, via tsx's dev-server codegen step) bind a
    # Unix domain socket inside node_modules, and Linux caps sun_path at
    # ~108 bytes. A long instance_id folded into the temp dir name was
    # occasionally enough, combined with deep node_modules nesting, to blow
    # that limit with a confusing EINVAL "listen" failure that looked like a
    # sandbox bug. A short, fixed prefix leaves headroom regardless of how
    # long a future instance_id gets.
    tmp_root = Path(tempfile.mkdtemp(prefix="tsbench-"))
    work_dir = tmp_root / "instance"
    sandbox = sandbox if sandbox is not None else LocalSandbox()

    def done(status: EvalStatus, **kwargs) -> EvalResult:
        return EvalResult(
            instance_id=instance.instance_id,
            status=status,
            wall_clock_seconds=time.monotonic() - start,
            **kwargs,
        )

    try:
        # Step 1: BUILD -- fresh materialize every call, on purpose. No
        # caching across runs: this harness's entire job is correctness, and
        # Step 9 (Docker layers) is where caching gets solved properly later.
        git.materialize_instance(mirror, instance.base_commit, work_dir)
        adapter = get_adapter(instance.language, work_dir)
        env = adapter.detect_environment(work_dir)  # always fresh, never trust instance.environment

        try:
            adapter.install(sandbox, env)
        except TimeoutError as e:
            return done(EvalStatus.TIMEOUT, stderr_tail=str(e))
        except Exception as e:
            # install() runs on bare base_commit, before any patch is
            # applied -- a compile failure here would mean the instance
            # itself is broken independent of anything a candidate did, a
            # real dataset-quality problem rather than "the agent failed."
            # In practice this should be rare to never for a validated
            # instance, but the check exists for the same reason it exists
            # on run_tests() below: never let a real, scoreable outcome be
            # silently swallowed into the infra_error bucket. If it fires
            # here on a real (non-transient) basis, that is itself a
            # significant finding worth investigating, not routing around.
            if adapter.is_compile_failure(e):
                f2p = {t: False for t in instance.fail_to_pass}
                p2p = {t: False for t in instance.pass_to_pass}
                return done(
                    EvalStatus.OK,
                    resolved=False,
                    fail_to_pass_results=f2p,
                    pass_to_pass_results=p2p,
                    stderr_tail=str(e)[-2000:],
                )
            return done(EvalStatus.INFRA_ERROR, stderr_tail=str(e)[-2000:])

        # Steps 3-4: apply the candidate patch, then reset any test files it
        # touched -- BEFORE injecting test_patch. This ordering stops an
        # agent from weakening tests to "pass", AND guarantees test_patch
        # always applies against pristine content.
        apply_result = git.try_apply_patch(work_dir, candidate_patch)
        if not apply_result.ok:
            return done(
                EvalStatus.PATCH_APPLY_FAILED,
                stdout_tail=apply_result.stdout[-2000:],
                stderr_tail=apply_result.stderr[-2000:],
            )

        touched = git.diff_touched_paths(candidate_patch)
        test_paths_touched = [p for p in touched if git.is_test_path(p)]
        git.restore_paths(mirror, instance.base_commit, work_dir, test_paths_touched)

        # Step 5: inject the answer-key tests
        test_patch_result = git.try_apply_patch(work_dir, instance.test_patch)
        if not test_patch_result.ok:
            return done(
                EvalStatus.TEST_PATCH_APPLY_FAILED,
                stdout_tail=test_patch_result.stdout[-2000:],
                stderr_tail=test_patch_result.stderr[-2000:],
            )

        # Step 6: run everything, filter to FAIL_TO_PASS/PASS_TO_PASS in
        # Python -- never scope the runner invocation itself (the -t flag
        # filters by bare test name, not "path::name", so it can't be handed
        # our test IDs directly; this mirrors what pipeline/validate.py
        # already does).
        try:
            raw = adapter.run_tests(sandbox, env, timeout=test_timeout)
        except TimeoutError as e:
            return done(EvalStatus.TIMEOUT, stderr_tail=str(e))
        except Exception as e:
            # A compile failure here is a REAL, scoreable outcome, not an
            # infra problem: for a compiled language, test_patch can require
            # an API surface only the correct fix adds (this is exactly what
            # T14's mining-time salvage handles for red_run against
            # base_commit -- see harness/java_adapter.py). At real-agent eval
            # time the same thing happens whenever a candidate patch is
            # incomplete: the injected tests simply won't compile against
            # it. Counting that as infra_error would silently exclude every
            # genuine "the agent didn't add the needed API" failure from the
            # resolved/unresolved denominator, inflating every model's score
            # on any instance that needed this salvage path. Every target
            # test correctly counts as not-passing (it never ran) rather
            # than being dropped from scoring entirely.
            if adapter.is_compile_failure(e):
                f2p = {t: False for t in instance.fail_to_pass}
                p2p = {t: False for t in instance.pass_to_pass}
                return done(
                    EvalStatus.OK,
                    resolved=False,
                    fail_to_pass_results=f2p,
                    pass_to_pass_results=p2p,
                    patch_strategy=apply_result.strategy,
                    reset_paths=test_paths_touched,
                    stderr_tail=str(e)[-2000:],
                )
            return done(EvalStatus.INFRA_ERROR, stderr_tail=str(e)[-2000:])

        outcomes = adapter.parse_results(raw, env.test_runner)
        f2p = {t: resolve_test_outcome(outcomes, t) for t in instance.fail_to_pass}
        p2p = {t: resolve_test_outcome(outcomes, t) for t in instance.pass_to_pass}
        resolved = all(f2p.values()) and all(p2p.values())

        # Step 7: SCORE
        return done(
            EvalStatus.OK,
            resolved=resolved,
            fail_to_pass_results=f2p,
            pass_to_pass_results=p2p,
            patch_strategy=apply_result.strategy,
            reset_paths=test_paths_touched,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
