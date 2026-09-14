"""T11: compute and persist contamination metadata (PR merge date) for every
currently validated instance, keyed by instance_id in a sidecar file --
kept separate from TaskInstance itself so the core schema stays a claim
about "is this a valid task," not a place for contamination disclosure.
"""

import json
from pathlib import Path

from pipeline import gitplumbing as git
from pipeline.contamination import merge_date, resolve_head_commit
from pipeline.schema import TaskInstance

ROOT = Path.home() / "projects" / "ts-bench"
MIRRORS_DIR = ROOT / "mirrors"
CACHE_DIR = ROOT / "scratch" / "mining_cache"
INSTANCES_FILE = ROOT / "datasets" / "instances.jsonl"
OUT_FILE = ROOT / "datasets" / "contamination.json"


def load_instances() -> list[TaskInstance]:
    with open(INSTANCES_FILE) as f:
        return [TaskInstance.model_validate_json(line) for line in f if line.strip()]


def main() -> None:
    instances = load_instances()
    metadata = {}

    for inst in instances:
        mirror = git.ensure_mirror(inst.repo, MIRRORS_DIR)
        head = resolve_head_commit(inst.instance_id, inst.repo, CACHE_DIR)
        date_str = merge_date(mirror, head)
        metadata[inst.instance_id] = {
            "repo": inst.repo,
            "head_commit": head,
            "pr_merge_date": date_str,
        }
        print(f"{inst.instance_id}: merged {date_str} ({head[:10]})")

    OUT_FILE.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote contamination metadata for {len(metadata)} instances -> {OUT_FILE}")


if __name__ == "__main__":
    main()
