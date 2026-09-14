"""T11: contamination metadata -- when was each validated instance's fix
merged, and is that plausibly within a given model's training data?

Contamination can't be eliminated, only disclosed: this computes a real,
git-derived merge date per instance and a documented risk rule against a
model's stated public knowledge cutoff, for the eventual T10 writeup to
report honestly. This is a disclosure mechanism, not a filter -- nothing
here removes an instance from the dataset.
"""

import json
from datetime import date, timedelta
from pathlib import Path

from pipeline import gitplumbing as git

# The 5 hand-picked zod candidates (T4) predate the miner and were validated
# before any GraphQL page was ever cached, so their merge commits can't be
# recovered from scratch/mining_cache the way mined instances' can. Recorded
# once here (copied straight from pipeline/run_validation.py's CANDIDATES)
# instead of re-deriving them some other way.
_ZOD_MERGE_COMMITS = {
    6530: "cafbee4772ef481611fef6f5fb9ed9a1b9597069",
    6587: "9446b5cc14c5bf137790f1f66abf602044871223",
    6572: "36f17960d1defca5d0896d9424f4e1059fbbf081",
    6534: "07c43e2a08f67082bd35c158d528d571a36094e0",
    6532: "f83ab51129038a2f868ee11dda906ed78ae2e478",
}


def _head_commit_from_mining_cache(cache_dir: Path, repo: str, pr_number: int) -> str | None:
    """Scan every cached GraphQL page for `repo` (written by pipeline.miner)
    for this PR's mergeCommit oid. Returns None if never seen."""
    repo_dir = cache_dir / repo.replace("/", "__")
    if not repo_dir.exists():
        return None
    for f in repo_dir.glob("*.json"):
        data = json.loads(f.read_text())
        for node in data.get("search", {}).get("nodes", []):
            if node and node.get("number") == pr_number:
                merge_commit = node.get("mergeCommit")
                if merge_commit:
                    return merge_commit["oid"]
    return None


def resolve_head_commit(instance_id: str, repo: str, cache_dir: Path) -> str:
    """The merged commit (squash or merge-commit) this instance's fix landed
    in -- needed because TaskInstance itself only stores base_commit."""
    pr_number = int(instance_id.rsplit("-", 1)[1])
    if repo == "colinhacks/zod" and pr_number in _ZOD_MERGE_COMMITS:
        return _ZOD_MERGE_COMMITS[pr_number]
    head = _head_commit_from_mining_cache(cache_dir, repo, pr_number)
    if head is None:
        raise ValueError(
            f"no known merge commit for {instance_id} -- it's neither a hand-picked zod "
            "candidate nor present in scratch/mining_cache; add it to _ZOD_MERGE_COMMITS "
            "or re-run the miner so its page gets cached again."
        )
    return head


def merge_date(mirror: Path, head_commit: str) -> str:
    """ISO-8601 date (YYYY-MM-DD) the fix was merged, from the head commit's
    own committer date -- the same moment GitHub shows as the merge time for
    a squash merge, and the merge commit's own time for a real merge commit."""
    out = git.run(["git", f"--git-dir={mirror}", "log", "-1", "--format=%cI", head_commit])
    return out.strip()[:10]


def contamination_risk(merge_date_str: str, model_cutoff_str: str, margin_days: int = 90) -> bool:
    """Is this instance a plausible contamination risk for a model with the
    given public knowledge cutoff (both "YYYY-MM-DD")?

    True whenever the fix could plausibly be in the model's training data:
    merged on/before the cutoff, OR merged up to `margin_days` after it. The
    margin exists because stated cutoffs are approximate (crawl-to-release
    lag, soft/rounded announced dates) -- a merge shortly "after" a cutoff is
    not a safe guarantee the model never saw it. This never rules an instance
    IN or OUT of the dataset; it's a label for the eventual per-model
    leaderboard writeup to disclose honestly.
    """
    merge_d = date.fromisoformat(merge_date_str)
    cutoff_d = date.fromisoformat(model_cutoff_str)
    return merge_d <= cutoff_d + timedelta(days=margin_days)
