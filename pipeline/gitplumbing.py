"""Thin wrappers around the git operations the validator and the eval runner need."""

import re
import subprocess
from dataclasses import dataclass
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


_COLOCATED_TEST_BASENAMES = {"test.ts", "test.tsx", "test.js", "test.jsx", "test.cjs", "test.mjs"}


def is_test_path(path: str) -> bool:
    # `.test.ts`-suffix (zod, trpc) and colocated-bare-`test.ts` (date-fns:
    # one `test.ts` per source file, in the same directory) are both real,
    # widely-used TS conventions -- neither implies the other. pytest's own
    # two conventions (T13) are additive on top, not exclusive with these:
    # a repo could in principle mix languages, and this function's only job
    # is "would a human call this a test file," not "which language."
    basename = path.rsplit("/", 1)[-1]
    return (
        ".test." in path
        or ".spec." in path
        or "/tests/" in path
        or "/__tests__/" in path
        or basename in _COLOCATED_TEST_BASENAMES
        or (basename.startswith("test_") and basename.endswith(".py"))
        or basename.endswith("_test.py")
    )


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


@dataclass(frozen=True)
class PatchApplyResult:
    ok: bool
    strategy: str | None  # "strict" | "fuzzy" | "empty", or None on failure
    stdout: str
    stderr: str


def try_apply_patch(dest: Path, patch_text: str) -> PatchApplyResult:
    """Never raises. An untrusted patch is data to score, not a contract to trust.

    Tries a leniency ladder: exact context match first, then a fuzzy match
    that tolerates minor line-offset drift. GNU patch's default fuzz is
    already 2, so both --fuzz values are set explicitly -- otherwise the two
    attempts would behave identically and the ladder would do nothing.
    """
    if not patch_text.strip():
        return PatchApplyResult(ok=True, strategy="empty", stdout="", stderr="")

    attempts = [
        ("strict", ["patch", "-p1", "--batch", "--fuzz=0", "-d", str(dest)]),
        ("fuzzy", ["patch", "-p1", "--batch", "--fuzz=3", "-d", str(dest)]),
    ]
    stdout = stderr = ""
    for name, cmd in attempts:
        result = subprocess.run(cmd, input=patch_text, capture_output=True, text=True)
        if result.returncode == 0:
            return PatchApplyResult(ok=True, strategy=name, stdout=result.stdout, stderr=result.stderr)
        stdout, stderr = result.stdout, result.stderr

    return PatchApplyResult(ok=False, strategy=None, stdout=stdout, stderr=stderr)


_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.MULTILINE)


def diff_touched_paths(patch_text: str) -> list[str]:
    """Return the file paths (post-image side) a unified diff touches.
    Best-effort: malformed input yields an empty list, never an exception."""
    return sorted({m.group(2) for m in _DIFF_GIT_RE.finditer(patch_text)})


def restore_paths(mirror: Path, base_commit: str, dest: Path, paths: list[str]) -> None:
    """Reset specific files back to their base_commit content, pulled straight
    from the mirror. No new git state needed anywhere -- the mirror is already
    the source of truth for "what did this file look like before anyone touched it"."""
    for rel_path in paths:
        result = subprocess.run(
            ["git", f"--git-dir={mirror}", "show", f"{base_commit}:{rel_path}"],
            capture_output=True,  # binary-safe: no text=True
        )
        target = dest / rel_path
        if result.returncode == 0:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(result.stdout)
        else:
            # didn't exist at base_commit -- candidate patch created it
            # (e.g. a new test file). Reset means it shouldn't be here.
            target.unlink(missing_ok=True)
