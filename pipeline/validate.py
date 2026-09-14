import json
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from harness.adapters import get_adapter
from harness.local_sandbox import LocalSandbox
from pipeline import gitplumbing as git
from pipeline.schema import Environment as SchemaEnvironment
from pipeline.schema import TaskInstance


@dataclass
class Candidate:
    repo: str
    pr_number: int
    issue_number: int
    merge_commit: str
    language: str = "typescript"
    # Relative path (from the materialized instance root) to the actual
    # package/module under test -- needed for a multi-module monorepo
    # (a TS workspace package, or a multi-module Maven reactor like gson's
    # gson/test-jpms/extras/... layout) where the repo root itself isn't
    # buildable/testable in isolation. None means single-package, the
    # common case, with zero behavior change.
    package_path: str | None = None


@dataclass
class Rejection:
    candidate: Candidate
    stage: str
    reason: str


def red_run(candidate: Candidate, mirrors_dir: Path, work_dir: Path) -> dict:
    mirror = git.ensure_mirror(candidate.repo, mirrors_dir)
    base, head = git.resolve_base_and_head(mirror, candidate.merge_commit)

    files = git.changed_files(mirror, base, head)
    test_files = [f for f in files if git.is_test_path(f)]
    non_test_files = [f for f in files if not git.is_test_path(f)]

    test_patch = git.extract_diff(mirror, base, head, test_files)
    gold_patch = git.extract_diff(mirror, base, head, non_test_files)

    dest = work_dir / f"{candidate.repo.replace('/', '__')}-{candidate.pr_number}"
    if dest.exists():
        shutil.rmtree(dest)
    git.materialize_instance(mirror, base, dest)
    git.apply_patch(dest, test_patch)

    package_path = dest / candidate.package_path if candidate.package_path else None
    sandbox = LocalSandbox()
    adapter = get_adapter(candidate.language, dest, package_path)
    env = adapter.detect_environment(dest)
    adapter.install(sandbox, env)

    per_test = run_tests_n_times(adapter, sandbox, env, n=3)
    results = deterministic_only(per_test)
    flaky_targets = [k for k in per_test if k not in results and k.split("::")[0] in test_files]

    candidate_f2p = [k for k in results if k.split("::")[0] in test_files and not results[k]]
    baseline_passing = {k for k in results if results[k]}

    return {
        "base": base,
        "head": head,
        "dest": dest,
        "language": candidate.language,
        "package_path": candidate.package_path,
        "test_files": test_files,
        "non_test_files": non_test_files,
        "test_patch": test_patch,
        "gold_patch": gold_patch,
        "candidate_f2p": candidate_f2p,
        "baseline_passing": baseline_passing,
        "flaky_targets": flaky_targets,
    }


def green_run(red_result: dict, n: int = 3) -> dict:
    dest = red_result["dest"]
    git.apply_patch(dest, red_result["gold_patch"])

    package_path = dest / red_result["package_path"] if red_result["package_path"] else None
    sandbox = LocalSandbox()
    adapter = get_adapter(red_result["language"], dest, package_path)
    env = adapter.detect_environment(dest)
    # no reinstall needed -- gold_patch only touches source files, not dependencies

    per_test = run_tests_n_times(adapter, sandbox, env, n=n)
    results = deterministic_only(per_test)
    flaky_targets = [
        k
        for k in per_test
        if k not in results and (k in red_result["candidate_f2p"] or k in red_result["baseline_passing"])
    ]

    still_failing = [k for k in red_result["candidate_f2p"] if not results.get(k, False)]
    regressed = [k for k in red_result["baseline_passing"] if not results.get(k, False)]

    return {
        "results": results,
        "still_failing": still_failing,
        "regressed": regressed,
        "flaky_targets": flaky_targets,
    }


def run_tests_n_times(adapter, sandbox, env, n: int = 3) -> dict[str, list[bool]]:
    """Return {test_id: [outcome_run1, outcome_run2, ...]}"""
    per_test: dict[str, list[bool]] = {}
    for _ in range(n):
        raw = adapter.run_tests(sandbox, env)
        results = adapter.parse_results(raw, env.test_runner)
        for k, v in results.items():
            per_test.setdefault(k, []).append(v)
    return per_test


def deterministic_only(per_test: dict[str, list[bool]]) -> dict[str, bool]:
    """Keep only tests whose outcome was identical across every run."""
    return {k: outcomes[0] for k, outcomes in per_test.items() if len(set(outcomes)) == 1}


def fetch_issue_text(repo: str, issue_number: int) -> str:
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    body = data["body"] or ""
    # Some issue reporters include the fix itself -- that would leak the
    # answer straight into the agent's prompt later. Blunt heuristic; always
    # read problem_statement by eye before trusting it in a real TaskInstance.
    for heading in ("### Suggested fix", "### Solution", "### Fix"):
        if heading in body:
            body = body.split(heading)[0]
    return f"{data['title']}\n\n{body.strip()}"


def to_schema_environment(harness_env) -> SchemaEnvironment:
    return SchemaEnvironment(
        runtime_version=harness_env.language_version,
        package_manager=harness_env.package_manager,
        install_cmd=" ".join(harness_env.install_cmd),
        # test_cmd_template is adapter-populated (see TypeScriptAdapter/
        # PythonAdapter's own detect_environment()) specifically so this
        # stays a plain field read, never an `if language == ...` here.
        test_cmd=" ".join(harness_env.test_cmd_template),
    )


def validate_candidate(candidate: Candidate, mirrors_dir: Path, work_dir: Path) -> TaskInstance | Rejection:
    red = red_run(candidate, mirrors_dir, work_dir)

    if red["flaky_targets"]:
        return Rejection(
            candidate, "red-flaky", f"target tests non-deterministic at base: {red['flaky_targets']}"
        )
    if not red["candidate_f2p"]:
        return Rejection(candidate, "red-gate", "no target tests failing at base_commit -- no real bug")

    green = green_run(red)

    if green["flaky_targets"]:
        return Rejection(
            candidate, "green-flaky", f"tests non-deterministic after gold patch: {green['flaky_targets']}"
        )
    if green["still_failing"]:
        return Rejection(candidate, "green-gate", f"gold patch did not fix: {green['still_failing']}")
    if green["regressed"]:
        return Rejection(
            candidate, "regression-gate", f"gold patch broke previously-passing tests: {green['regressed']}"
        )

    problem_statement = fetch_issue_text(candidate.repo, candidate.issue_number)
    package_path = red["dest"] / candidate.package_path if candidate.package_path else None
    adapter = get_adapter(candidate.language, red["dest"], package_path)
    harness_env = adapter.detect_environment(red["dest"])

    try:
        return TaskInstance(
            instance_id=f"{candidate.repo.replace('/', '__')}-{candidate.pr_number}",
            repo=candidate.repo,
            base_commit=red["base"],
            problem_statement=problem_statement,
            gold_patch=red["gold_patch"],
            test_patch=red["test_patch"],
            fail_to_pass=red["candidate_f2p"],
            pass_to_pass=sorted(red["baseline_passing"]),
            environment=to_schema_environment(harness_env),
            language=candidate.language,
        )
    except Exception as e:
        return Rejection(candidate, "schema", f"TaskInstance validation failed: {e}")
