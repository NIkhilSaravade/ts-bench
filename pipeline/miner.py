"""GitHub GraphQL miner: finds merged PRs that close an issue AND touch a test file.

Feeds straight into `pipeline.validate.Candidate` / `validate_candidate` -- the
miner's whole job is finding *promising* raw material, not judging it. T4's
validator (gold-fails-at-base, gold-patch-fixes, no regressions) is the real
judge; a PR that "closes #N" but turns out to be a refactor or a doc fix is
expected to be rejected there, not filtered out here.
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from pipeline.gitplumbing import is_test_path
from pipeline.validate import Candidate

GRAPHQL_URL = "https://api.github.com/graphql"

# `search(type: ISSUE, ...)` is GitHub's shared issue+PR search endpoint;
# `is:pr` in the query string is what narrows it to pull requests.
# `closingIssuesReferences` is the actual "closes #N" linkage GitHub tracks
# (not a text regex over the PR body), and `files` lets us check for a
# touched test file without a second round-trip per candidate.
_QUERY = """
query($searchQuery: String!, $cursor: String) {
  rateLimit { remaining resetAt }
  search(query: $searchQuery, type: ISSUE, first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        mergeCommit { oid }
        closingIssuesReferences(first: 5) { nodes { number } }
        files(first: 100) { nodes { path } }
      }
    }
  }
}
"""


def _graphql(token: str, query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "ts-bench-miner",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub GraphQL request failed: {e.code} {e.read().decode()}") from e
    if "errors" in body:
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    return body["data"]


def _cache_path(cache_dir: Path, repo: str, cursor: str | None) -> Path:
    return cache_dir / repo.replace("/", "__") / f"{cursor or 'start'}.json"


def _fetch_page(token: str, repo: str, cursor: str | None, cache_dir: Path) -> dict:
    """Cached per (repo, cursor) so a rerun costs zero API calls unless max_pages grows."""
    cache_file = _cache_path(cache_dir, repo, cursor)
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    search_query = f"repo:{repo} is:pr is:merged sort:created-desc"
    data = _graphql(token, _QUERY, {"searchQuery": search_query, "cursor": cursor})

    remaining = data["rateLimit"]["remaining"]
    if remaining < 50:
        print(f"  rate limit low ({remaining} remaining, resets {data['rateLimit']['resetAt']}) -- pausing")
        time.sleep(5)

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data))
    return data


def mine_repo(repo: str, token: str, cache_dir: Path, max_pages: int = 6) -> list[Candidate]:
    """Scan up to `max_pages` * 50 most-recently-created merged PRs in `repo`,
    returning one Candidate per PR that both closes an issue and touches a
    test file. Each page is cached to disk keyed by its GraphQL cursor."""
    candidates: list[Candidate] = []
    cursor: str | None = None
    for _ in range(max_pages):
        data = _fetch_page(token, repo, cursor, cache_dir)
        search = data["search"]
        for node in search["nodes"]:
            if not node:
                continue
            merge_commit = node.get("mergeCommit")
            issues = (node.get("closingIssuesReferences") or {}).get("nodes") or []
            files = (node.get("files") or {}).get("nodes") or []
            if not merge_commit or not issues:
                continue
            if not any(is_test_path(f["path"]) for f in files):
                continue
            candidates.append(
                Candidate(
                    repo=repo,
                    pr_number=node["number"],
                    issue_number=issues[0]["number"],
                    merge_commit=merge_commit["oid"],
                )
            )
        if not search["pageInfo"]["hasNextPage"]:
            break
        cursor = search["pageInfo"]["endCursor"]
    return candidates
