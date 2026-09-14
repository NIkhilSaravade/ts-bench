import argparse
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.stats import compute_model_stats


def main():
    parser = argparse.ArgumentParser(
        description="Compute resolved%, pass@k, bootstrap variance, and cost per model from a repeats JSONL."
    )
    parser.add_argument("--in", dest="in_path", required=True)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--out", default=None, help="Optional path to write the full per-task breakdown as JSON"
    )
    parser.add_argument("--verbose", action="store_true", help="Also print a line per task")
    args = parser.parse_args()

    records = [json.loads(line) for line in Path(args.in_path).read_text().splitlines() if line.strip()]
    models = sorted({r["model"] for r in records})

    all_stats = {}
    header = (
        f"{'model':<20}{'tasks':>6}{'N':>6}{'resolved%':>11}"
        f"{'pass@' + str(args.k):>10}{'±stderr':>10}{'cost($)':>10}"
    )
    print(header)
    print("-" * len(header))
    for model in models:
        stats = compute_model_stats(records, model, args.k, args.bootstrap, args.seed)
        all_stats[model] = stats
        print(
            f"{model:<20}{stats.num_tasks:>6}{stats.total_attempts:>6}"
            f"{stats.resolved_rate * 100:>10.1f}%{stats.mean_pass_at_k:>10.3f}"
            f"{stats.mean_pass_at_k_stderr:>10.3f}{stats.total_cost_usd:>10.2f}"
        )
        if args.verbose:
            for t in stats.per_task:
                print(
                    f"    {t.instance_id:<30} n={t.n:<4} c={t.c:<4} "
                    f"resolved_rate={t.resolved_rate:.3f} pass@{args.k}={t.pass_at_k:.3f} "
                    f"(boot_std={t.pass_at_k_bootstrap_std:.3f})"
                )

    if args.out:
        serializable = {m: dataclasses.asdict(s) for m, s in all_stats.items()}
        Path(args.out).write_text(json.dumps(serializable, indent=2))
        print(f"\nFull per-task breakdown written to {args.out}")


if __name__ == "__main__":
    main()
