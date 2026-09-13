"""The reference agent's own throwaway workspace.

Separate from the git-free scoring instance harness/eval_runner.py's
evaluate() materializes internally. That one must never have a .git — the
agent's patch is applied to it from the outside, as a string. This one is
the opposite: the only way to get a patch out of a freeform explore/edit
loop is to diff the end state against a known starting point, so it's
deliberately git-init'd. Deliberately safe, too: git init here creates a
brand-new, single-commit history with nothing to leak — materialize_instance
already stripped everything but the file tree at base_commit before we ever
touch git.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pipeline.gitplumbing import materialize_instance
from pipeline.schema import TaskInstance


def _mirror_path(instance: TaskInstance, mirrors_dir: Path) -> Path:
    # Same resolution harness/eval_runner.py::evaluate() uses. Keep these
    # two expressions in sync if that convention ever changes.
    return mirrors_dir / f"{instance.repo.replace('/', '__')}.git"


@contextmanager
def agent_workspace(instance: TaskInstance, mirrors_dir: Path) -> Iterator[Path]:
    """Materialize a throwaway, git-inited copy of `instance` for the agent
    to explore and edit freely, and delete it on exit no matter what —
    including if the agent loop raises partway through.

    Yields the workspace path with a single baseline commit already made,
    so every subsequent edit shows up as a diff against HEAD.
    """
    mirror = _mirror_path(instance, mirrors_dir)

    # Same mkdtemp-then-not-yet-existing-subdir dance as eval_runner.py,
    # for the same reason: mkdtemp() already creates the dir it returns,
    # but materialize_instance refuses to run if dest already exists.
    tmp_root = Path(tempfile.mkdtemp(prefix=f"tsbench-agent-{instance.instance_id}-"))
    workspace = tmp_root / "workspace"

    try:
        materialize_instance(mirror, instance.base_commit, workspace)

        _run_git(workspace, ["init", "-q"])
        _run_git(workspace, ["add", "-A"])
        _run_git(
            workspace,
            [
                "-c",
                "user.email=agent@ts-bench.local",
                "-c",
                "user.name=ts-bench-agent",
                "commit",
                "-q",
                "-m",
                "baseline: materialized instance",
            ],
        )

        yield workspace
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def extract_patch(workspace: Path) -> str:
    """Everything the agent changed, as a unified diff against the
    workspace's baseline commit. Call this once, after the agent loop ends
    (explicit submit or budget exhaustion) — never mid-loop."""
    result = _run_git(workspace, ["diff", "--no-color", "HEAD"])
    return result.stdout


def _run_git(cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}:\n{result.stderr}")
    return result
