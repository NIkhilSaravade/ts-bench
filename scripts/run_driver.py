import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.driver import run_and_evaluate
from pipeline.schema import TaskInstance

MIRRORS_DIR = Path("mirrors")
DATASET = Path("datasets/instances.jsonl")


def load_instances(selector: str) -> list[TaskInstance]:
    lines = DATASET.read_text().splitlines()
    if selector == "all":
        selected = lines
    else:
        selected = []
        for tok in selector.split(","):
            tok = tok.strip()
            if tok.isdigit():
                selected.append(lines[int(tok)])
            else:
                matches = [line for line in lines if json.loads(line).get("instance_id") == tok]
                if not matches:
                    raise SystemExit(f"No instance matching {tok!r}")
                selected.append(matches[0])
    return [TaskInstance.model_validate_json(line) for line in selected]


def main():
    parser = argparse.ArgumentParser(description="Run one or more models over one or more task instances.")
    parser.add_argument(
        "--models", required=True, help="Comma-separated model names, e.g. mock/gold,mock/empty"
    )
    parser.add_argument(
        "--instances", default="all", help="Comma-separated indices/instance_ids, or 'all' (default)"
    )
    parser.add_argument("--wall-clock-seconds", type=float, default=None, help="Per-run wall clock budget")
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Run each (model, instance) pair this many times (T9: pass@k needs n >= k repeats per task)",
    )
    parser.add_argument("--out", required=True, help="Output JSONL file (appended to; resumable)")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",")]
    instances = load_instances(args.instances)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    already_done = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            # .get("repeat", 0): pre-T9 result files never wrote a "repeat"
            # field -- every row there was implicitly attempt 0.
            already_done.add((rec["model"], rec["instance_id"], rec.get("repeat", 0)))

    with out_path.open("a") as f:
        for model in models:
            for instance in instances:
                for repeat in range(args.repeats):
                    key = (model, instance.instance_id, repeat)
                    if key in already_done:
                        print(
                            f"[skip] {model} / {instance.instance_id} / repeat={repeat} "
                            f"(already in {out_path})"
                        )
                        continue
                    print(f"[run]  {model} / {instance.instance_id} / repeat={repeat}")
                    result = run_and_evaluate(
                        model,
                        instance,
                        MIRRORS_DIR,
                        wall_clock_seconds=args.wall_clock_seconds,
                    )
                    record = {
                        "model": model,
                        "instance_id": result.instance_id,
                        "repeat": repeat,
                        "status": str(result.status),
                        "resolved": result.resolved,
                        "patch_strategy": result.patch_strategy,
                        "wall_clock_seconds": result.wall_clock_seconds,
                        "cost_usd": result.cost_usd,
                        "tokens_used": result.tokens_used,
                        "fail_to_pass_results": result.fail_to_pass_results,
                        "pass_to_pass_results": result.pass_to_pass_results,
                        "stderr_tail": result.stderr_tail,
                    }
                    f.write(json.dumps(record) + "\n")
                    f.flush()
                    print(
                        f"       -> status={result.status} resolved={result.resolved} cost={result.cost_usd}"
                    )


if __name__ == "__main__":
    main()
