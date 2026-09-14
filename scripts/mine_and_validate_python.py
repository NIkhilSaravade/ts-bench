"""T13: mine merged PRs from real Python repos and validate candidates
through the same T4 validator used for TypeScript, proving the language
seam is a genuine drop-in. Mirrors scripts/mine_and_validate.py exactly,
just with language="python" threaded through.
"""

import json
import os
import sys
from pathlib import Path

from pipeline.miner import mine_repo
from pipeline.schema import TaskInstance
from pipeline.validate import validate_candidate

REPOS_TO_MINE = ["arrow-py/arrow", "jd/tenacity"]
MINE_MAX_PAGES = 15
MAX_CANDIDATES_PER_REPO = 30
TARGET_VALIDATED_PER_REPO = 3

ROOT = Path.home() / "projects" / "ts-bench"
MIRRORS_DIR = ROOT / "mirrors"
WORK_DIR = ROOT / "instances"
CACHE_DIR = ROOT / "scratch" / "mining_cache"
OUT_DIR = ROOT / "datasets"


def load_existing_instances() -> list[TaskInstance]:
    path = OUT_DIR / "instances.jsonl"
    if not path.exists():
        return []
    return [TaskInstance.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]


def load_existing_rejections() -> list[dict]:
    path = OUT_DIR / "rejections.json"
    if not path.exists() or not path.read_text().strip():
        return []
    return json.loads(path.read_text())


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN not set -- export it or add it to .env first.", file=sys.stderr)
        sys.exit(1)

    existing = load_existing_instances()
    existing_ids = {i.instance_id for i in existing}
    rejections = load_existing_rejections()
    already_seen = {(r["repo"], r["pr_number"]) for r in rejections}
    already_seen |= {(i.repo, int(i.instance_id.rsplit("-", 1)[1])) for i in existing}

    new_instances: list[TaskInstance] = []

    for repo in REPOS_TO_MINE:
        print(f"mining {repo} ...", flush=True)
        candidates = mine_repo(repo, token, CACHE_DIR, max_pages=MINE_MAX_PAGES, language="python")
        print(f"  {len(candidates)} raw candidates found (merged PR, closes issue, touches test file)")

        validated_this_repo = 0
        attempted_this_repo = 0
        for c in candidates:
            if (c.repo, c.pr_number) in already_seen:
                continue
            if attempted_this_repo >= MAX_CANDIDATES_PER_REPO:
                print(f"  hit attempt cap ({MAX_CANDIDATES_PER_REPO}) for {repo}, moving on")
                break
            if validated_this_repo >= TARGET_VALIDATED_PER_REPO:
                print(f"  reached target ({TARGET_VALIDATED_PER_REPO}) validated instances for {repo}")
                break

            attempted_this_repo += 1
            print(f"  validating {c.repo}#{c.pr_number} (issue #{c.issue_number}) ...", flush=True)
            try:
                result = validate_candidate(c, MIRRORS_DIR, WORK_DIR)
            except Exception as e:  # noqa: BLE001 -- a broken candidate must not kill the whole mining run
                print(f"    -> ERROR (treated as rejection): {e}")
                rejections.append(
                    {"repo": c.repo, "pr_number": c.pr_number, "stage": "exception", "reason": str(e)}
                )
                already_seen.add((c.repo, c.pr_number))
                continue

            already_seen.add((c.repo, c.pr_number))
            if isinstance(result, TaskInstance):
                print(f"    -> VALIDATED: {result.instance_id}")
                new_instances.append(result)
                existing_ids.add(result.instance_id)
                validated_this_repo += 1
            else:
                print(f"    -> REJECTED [{result.stage}]: {result.reason}")
                rejections.append(
                    {
                        "repo": c.repo,
                        "pr_number": c.pr_number,
                        "stage": result.stage,
                        "reason": result.reason,
                    }
                )

    all_instances = existing + new_instances
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "instances.jsonl").write_text("\n".join(i.model_dump_json() for i in all_instances) + "\n")
    (OUT_DIR / "rejections.json").write_text(json.dumps(rejections, indent=2))
    print(
        f"\n{len(new_instances)} newly validated ({len(all_instances)} total instances), "
        f"{len(rejections)} total rejections"
    )


if __name__ == "__main__":
    main()
