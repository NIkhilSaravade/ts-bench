"""Thin wrappers around the git operations the validator needs."""

import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
    return result.stdout


def ensure_mirror(repo: str, mirrors_dir: Path) -> Path:
    """repo like 'colinhacks/zod'. Clones once; fetches if it already exists."""
    mirror_path = mirrors_dir / f"{repo.replace('/', '__')}.git"
    if mirror_path.exists():
        run(["git", f"--git-dir={mirror_path}", "fetch", "--all", "--prune"])
    else:
        mirror_path.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--mirror", f"https://github.com/{repo}.git", str(mirror_path)])
    return mirror_path


def commit_parents(mirror: Path, commit: str) -> list[str]:
    out = run(["git", f"--git-dir={mirror}", "log", "-n", "1", "--format=%P", commit])
    return out.strip().split()


def full_hash(mirror: Path, ref: str) -> str:
    return run(["git", f"--git-dir={mirror}", "rev-parse", ref]).strip()


def resolve_base_and_head(mirror: Path, merge_commit: str) -> tuple[str, str]:
    """Given a merge/squash commit (short or full hash), return (base_commit, head_commit), both full."""
    head = full_hash(mirror, merge_commit)
    parents = commit_parents(mirror, head)
    if len(parents) == 1:
        return parents[0], head  # squash merge
    elif len(parents) == 2:
        return parents[0], parents[1]  # real merge commit
    raise ValueError(f"{head} has {len(parents)} parents — not a normal merge")


def changed_files(mirror: Path, base: str, head: str) -> list[str]:
    out = run(["git", f"--git-dir={mirror}", "diff", "--name-only", base, head])
    return [line for line in out.splitlines() if line]


def is_test_path(path: str) -> bool:
    return ".test." in path or ".spec." in path or "/tests/" in path or "/__tests__/" in path


def extract_diff(mirror: Path, base: str, head: str, pathspecs: list[str]) -> str:
    return run(["git", f"--git-dir={mirror}", "diff", base, head, "--", *pathspecs])


def materialize_instance(mirror: Path, commit: str, dest: Path) -> None:
    """Extract a plain, git-free file tree at `commit` into `dest`."""
    if dest.exists():
        raise FileExistsError(f"{dest} already exists — validator must start clean")
    dest.mkdir(parents=True)
    archive = subprocess.run(
        ["git", f"--git-dir={mirror}", "archive", commit],
        capture_output=True,
        check=True,
    )
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)


def apply_patch(dest: Path, patch_text: str) -> None:
    if not patch_text.strip():
        return
    result = subprocess.run(
        ["patch", "-p1", "-d", str(dest)],
        input=patch_text,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"patch failed to apply in {dest}:\n{result.stdout}\n{result.stderr}")
