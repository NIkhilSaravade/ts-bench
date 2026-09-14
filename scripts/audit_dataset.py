"""T11: flakiness + reproducibility audit.

Standalone, run-on-demand check that the CURRENT full dataset still holds
up -- not just at initial validation time. Two distinct risks, one script:

  - Flakiness: an instance's FAIL_TO_PASS/PASS_TO_PASS split was only ever
    confirmed once, at validation time, and could have been a lucky run.
    Running the gold/empty gate N times and requiring identical outcomes
    every time catches a "sometimes passes" instance.
  - Reproducibility/drift: dependency versions move on after validation, and
    an instance that passed the gate in September can silently stop passing
    in December for reasons that have nothing to do with any agent.
    evaluate() always re-materializes the instance fresh from its mirror on
    every call (nothing is cached or reused from a previous validation run),
    so simply calling it again right now already re-proves this from scratch.

An instance that fails or disagrees with itself even once is QUARANTINED
(flagged in the report), never silently dropped -- deciding what to do with
a quarantined instance is a human call, not this script's.
"""

import json
import sys
from pathlib import Path

from harness.eval_runner import evaluate
from pipeline.schema import TaskInstance

N_RUNS = 3
MIRRORS_DIR = Path.home() / "projects" / "ts-bench" / "mirrors"
INSTANCES_FILE = Path.home() / "projects" / "ts-bench" / "datasets" / "instances.jsonl"
REPORT_FILE = Path.home() / "projects" / "ts-bench" / "datasets" / "rigor_audit_report.json"


def load_instances() -> list[TaskInstance]:
    with open(INSTANCES_FILE) as f:
        return [TaskInstance.model_validate_json(line) for line in f if line.strip()]


def audit_instance(inst: TaskInstance, n_runs: int = N_RUNS) -> dict:
    gold_runs = []
    empty_runs = []
    for _ in range(n_runs):
        gold = evaluate(inst, inst.gold_patch, MIRRORS_DIR)
        gold_runs.append({"status": gold.status.value, "resolved": gold.resolved})
        empty = evaluate(inst, "", MIRRORS_DIR)
        empty_runs.append({"status": empty.status.value, "resolved": empty.resolved})

    gold_deterministic = len({r["resolved"] for r in gold_runs}) == 1
    empty_deterministic = len({r["resolved"] for r in empty_runs}) == 1
    gold_all_resolved = all(r["resolved"] for r in gold_runs)
    empty_none_resolved = not any(r["resolved"] for r in empty_runs)

    clean = gold_deterministic and empty_deterministic and gold_all_resolved and empty_none_resolved
    return {
        "instance_id": inst.instance_id,
        "clean": clean,
        "gold_runs": gold_runs,
        "empty_runs": empty_runs,
    }


def main() -> None:
    instances = load_instances()
    results = []
    quarantined = []

    for inst in instances:
        print(f"auditing {inst.instance_id} ({N_RUNS}x gold, {N_RUNS}x empty) ...", flush=True)
        result = audit_instance(inst)
        results.append(result)
        status = "CLEAN" if result["clean"] else "QUARANTINED"
        print(f"  -> {status}")
        if not result["clean"]:
            quarantined.append(inst.instance_id)

    REPORT_FILE.write_text(json.dumps({"n_runs": N_RUNS, "results": results}, indent=2))
    print(f"\nreport written -> {REPORT_FILE}")
    print(f"{len(instances) - len(quarantined)}/{len(instances)} instances clean.")

    if quarantined:
        print(f"QUARANTINED: {quarantined}")
        sys.exit(1)


if __name__ == "__main__":
    main()
