"""Step 10 verification: the failure-mode taxonomy and the anti-cheat reset
mechanism -- neither is exercised by scripts/run_gate.py, since gold_patch is
defined (in validate.py) to only ever touch non-test files, so restore_paths
is never actually invoked during that gate run."""

import tempfile
import time
from pathlib import Path

import pytest

from harness.eval_result import EvalStatus
from harness.eval_runner import evaluate
from harness.local_sandbox import LocalSandbox
from pipeline import gitplumbing as git
from pipeline.schema import TaskInstance

MIRRORS_DIR = Path.home() / "projects/ts-bench/mirrors"
INSTANCES_FILE = Path.home() / "projects/ts-bench/datasets/instances.jsonl"


@pytest.fixture(scope="module")
def instances() -> list[TaskInstance]:
    with open(INSTANCES_FILE) as f:
        return [TaskInstance.model_validate_json(line) for line in f if line.strip()]


@pytest.fixture(scope="module")
def one_instance(instances) -> TaskInstance:
    return instances[0]


def _fresh_instance_dir(td: str, mirror: Path, base_commit: str) -> Path:
    # mkdtemp/TemporaryDirectory already CREATE the directory they return,
    # but materialize_instance refuses to run if dest already exists -- same
    # trap eval_runner.py hit. Always materialize into a not-yet-existing
    # subdirectory of the temp dir.
    dest = Path(td) / "instance"
    git.materialize_instance(mirror, base_commit, dest)
    return dest


def test_try_apply_patch_valid(one_instance):
    mirror = MIRRORS_DIR / f"{one_instance.repo.replace('/', '__')}.git"
    with tempfile.TemporaryDirectory() as td:
        dest = _fresh_instance_dir(td, mirror, one_instance.base_commit)
        result = git.try_apply_patch(dest, one_instance.gold_patch)
        assert result.ok
        assert result.strategy == "strict"


def test_try_apply_patch_malformed():
    with tempfile.TemporaryDirectory() as td:
        result = git.try_apply_patch(Path(td), "this is not a diff at all\njust garbage\n")
        assert not result.ok
        assert result.strategy is None


def test_try_apply_patch_empty():
    with tempfile.TemporaryDirectory() as td:
        result = git.try_apply_patch(Path(td), "")
        assert result.ok
        assert result.strategy == "empty"


def test_diff_touched_paths_real(one_instance):
    paths = git.diff_touched_paths(one_instance.test_patch)
    assert len(paths) > 0
    assert all(git.is_test_path(p) for p in paths)


def test_diff_touched_paths_garbage():
    assert git.diff_touched_paths("not a diff\nno headers here\n") == []


def test_restore_paths_undoes_tampering(one_instance):
    """The core anti-cheat mechanism -- proven in isolation since the gate
    can't reach it (see module docstring)."""
    mirror = MIRRORS_DIR / f"{one_instance.repo.replace('/', '__')}.git"
    test_file = git.diff_touched_paths(one_instance.test_patch)[0]

    with tempfile.TemporaryDirectory() as td:
        dest = _fresh_instance_dir(td, mirror, one_instance.base_commit)

        pristine = (dest / test_file).read_bytes()
        (dest / test_file).write_bytes(b"// TAMPERED BY AGENT\n" + pristine)
        assert (dest / test_file).read_bytes() != pristine

        git.restore_paths(mirror, one_instance.base_commit, dest, [test_file])
        assert (dest / test_file).read_bytes() == pristine


def test_restore_paths_deletes_newly_created_file(one_instance):
    """A path that didn't exist at base_commit should be deleted on reset,
    not error trying to restore content that never existed."""
    mirror = MIRRORS_DIR / f"{one_instance.repo.replace('/', '__')}.git"
    with tempfile.TemporaryDirectory() as td:
        dest = _fresh_instance_dir(td, mirror, one_instance.base_commit)
        new_file = dest / "src__totally_new.spec.ts"
        new_file.write_text("// agent invented this file\n")

        git.restore_paths(mirror, one_instance.base_commit, dest, ["src__totally_new.spec.ts"])
        assert not new_file.exists()


def test_local_sandbox_timeout_kills_promptly():
    sandbox = LocalSandbox()
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        sandbox.run(["sleep", "5"], cwd=Path(tempfile.gettempdir()), timeout=1)
    elapsed = time.monotonic() - start
    assert elapsed < 3, f"took {elapsed:.1f}s -- timeout isn't actually killing the process"


def test_evaluate_malformed_patch_never_crashes(one_instance):
    """Slow (runs a full install) but it's the only way to prove the whole
    evaluate() pipeline degrades gracefully end-to-end, not just try_apply_patch
    in isolation."""
    result = evaluate(one_instance, "this is not a diff\ngarbage text\n", MIRRORS_DIR)
    assert result.status == EvalStatus.PATCH_APPLY_FAILED
    assert result.resolved is False


def test_evaluate_install_stage_compile_failure_is_resolved_false(monkeypatch, one_instance):
    """Symmetry check: install() runs before run_tests() and can also raise
    a compile-type failure (a real, if rare, occurrence in practice -- see
    docs/step7-real-model-run.md's Bug #2/#3 notes). This must be classified
    the same way as a run_tests()-stage compile failure, not fall through to
    the unconditional infra_error branch that only got fixed for run_tests()
    the first time around. A real install()-stage compile failure isn't
    reliably reproducible on demand, so this uses a fake adapter instead."""

    class _FakeCompileFailure(Exception):
        pass

    class _FakeAdapter:
        def detect_environment(self, repo_path):
            from harness.language_adapter import Environment

            return Environment(
                language_version="1",
                package_manager="fake",
                test_runner="fake",
                install_cmd=[],
                test_cmd_template=[],
            )

        def install(self, sandbox, env):
            raise _FakeCompileFailure("pretend javac blew up during install()")

        def run_tests(self, sandbox, env, test_ids=None, timeout=300):
            raise AssertionError("should never reach run_tests()")

        def parse_results(self, raw_output, runner="fake"):
            return {}

        def is_compile_failure(self, error):
            return isinstance(error, _FakeCompileFailure)

    monkeypatch.setattr("harness.eval_runner.get_adapter", lambda language, work_dir: _FakeAdapter())

    result = evaluate(one_instance, one_instance.gold_patch, MIRRORS_DIR)
    assert result.status == EvalStatus.OK
    assert result.resolved is False
    assert result.fail_to_pass_results
    assert all(v is False for v in result.fail_to_pass_results.values())


def test_evaluate_compile_failure_is_resolved_false_not_infra_error(instances):
    """Real-agent-run finding (never exercised before a first real Java run,
    since the gate only ever scores the gold patch, which always compiles):
    jhy__jsoup-2602 is one of T14's "salvaged" instances -- the gold patch
    adds HtmlTreeBuilder.insertNode(), which test_patch's injected test needs
    just to COMPILE. An empty (or any incomplete) candidate patch can't add
    that method, so test-compile fails outright, before any test ever runs.
    That's a real, legitimate "the agent didn't solve it" -- it must score
    resolved=False, not infra_error (which would silently drop it from the
    resolved/unresolved denominator and inflate the model's real score)."""
    jsoup_2602 = next(i for i in instances if i.instance_id == "jhy__jsoup-2602")
    result = evaluate(jsoup_2602, "", MIRRORS_DIR)
    assert result.status == EvalStatus.OK
    assert result.resolved is False
    assert result.fail_to_pass_results
    assert all(v is False for v in result.fail_to_pass_results.values())
