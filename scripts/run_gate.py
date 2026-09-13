"""The critical gate for Step 10: prove the RUNNER (not just the validator)
is correct. Gold patch must resolve every instance; empty patch must resolve
none. If either fails, there is a harness bug -- fix it, don't move on."""

import sys
from pathlib import Path

from harness.eval_runner import evaluate
from pipeline.schema import TaskInstance

MIRRORS_DIR = Path.home() / "projects/ts-bench/mirrors"
INSTANCES_FILE = Path.home() / "projects/ts-bench/datasets/instances.jsonl"


def load_instances() -> list[TaskInstance]:
    with open(INSTANCES_FILE) as f:
        return [TaskInstance.model_validate_json(line) for line in f if line.strip()]


def main() -> None:
    instances = load_instances()
    failures = []

    for inst in instances:
        gold = evaluate(inst, inst.gold_patch, MIRRORS_DIR)
        print(f"{inst.instance_id} [gold]  status={gold.status.value} resolved={gold.resolved}")
        if not gold.resolved:
            failures.append((inst.instance_id, "gold", gold))

        empty = evaluate(inst, "", MIRRORS_DIR)
        print(f"{inst.instance_id} [empty] status={empty.status.value} resolved={empty.resolved}")
        if empty.resolved:
            failures.append((inst.instance_id, "empty", empty))

    if failures:
        print(f"\nGATE FAILED: {len(failures)} case(s)")
        for iid, kind, r in failures:
            print(
                f"  {iid} [{kind}]: status={r.status.value} "
                f"f2p={r.fail_to_pass_results} p2p={r.pass_to_pass_results}"
            )
        sys.exit(1)

    print(f"\nGATE PASSED: {len(instances)} instances -- gold resolves all, empty resolves none.")


if __name__ == "__main__":
    main()
