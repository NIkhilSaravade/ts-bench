import json
from pathlib import Path

from pipeline.schema import TaskInstance
from pipeline.validate import Candidate, validate_candidate

CANDIDATES = [
    Candidate(
        repo="colinhacks/zod",
        pr_number=6530,
        issue_number=6526,
        merge_commit="cafbee4772ef481611fef6f5fb9ed9a1b9597069",
    ),
    Candidate(
        repo="colinhacks/zod",
        pr_number=6587,
        issue_number=6585,
        merge_commit="9446b5cc14c5bf137790f1f66abf602044871223",
    ),
    Candidate(
        repo="colinhacks/zod",
        pr_number=6572,
        issue_number=6557,
        merge_commit="36f17960d1defca5d0896d9424f4e1059fbbf081",
    ),
    Candidate(
        repo="colinhacks/zod",
        pr_number=6534,
        issue_number=6528,
        merge_commit="07c43e2a08f67082bd35c158d528d571a36094e0",
    ),
    Candidate(
        repo="colinhacks/zod",
        pr_number=6532,
        issue_number=6515,
        merge_commit="f83ab51129038a2f868ee11dda906ed78ae2e478",
    ),
]

MIRRORS_DIR = Path.home() / "projects/ts-bench/mirrors"
WORK_DIR = Path.home() / "projects/ts-bench/instances"
OUT_DIR = Path.home() / "projects/ts-bench/datasets"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    instances = []
    rejections = []

    for c in CANDIDATES:
        print(f"validating {c.repo}#{c.pr_number} ...", flush=True)
        result = validate_candidate(c, MIRRORS_DIR, WORK_DIR)
        if isinstance(result, TaskInstance):
            print(f"  -> VALIDATED: {result.instance_id}")
            instances.append(result)
        else:
            print(f"  -> REJECTED [{result.stage}]: {result.reason}")
            rejections.append(
                {"repo": c.repo, "pr_number": c.pr_number, "stage": result.stage, "reason": result.reason}
            )

    (OUT_DIR / "instances.jsonl").write_text("\n".join(i.model_dump_json() for i in instances) + "\n")
    (OUT_DIR / "rejections.json").write_text(json.dumps(rejections, indent=2))
    print(f"\n{len(instances)} validated, {len(rejections)} rejected")


if __name__ == "__main__":
    main()
