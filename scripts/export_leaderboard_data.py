"""Export the real benchmark results as one small JSON file for the leaderboard site (T10).

Reads the raw run files under results/ (the big one is gitignored, local only), the dataset, and
the contamination sidecar; writes leaderboard/data/results.json, which IS committed so the site
can be rebuilt on any machine without the 130MB raw file.

Every number on the site comes from this file. Nothing is typed in by hand.

Scoring rules (same as the harness and pipeline/stats.py):
  - an attempt counts as resolved only if status == "ok" and every fail_to_pass and pass_to_pass
    test passes;
  - infra_error attempts are excluded from the denominator (our failure, not the model's);
  - timeout and patch_apply_failed count as unresolved and stay in the denominator.

Usage: python3 scripts/export_leaderboard_data.py
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUT = ROOT / "leaderboard" / "data" / "results.json"
DATASET_VERSION = "v0.2"

# One entry per model that was PLANNED for the real-model run, whether or not it produced data.
# `source` is the raw file; planned_attempts is instances x repeats that were intended.
MODELS = [
    {
        "id": "openrouter/anthropic/claude-haiku-4.5",
        "name": "Claude Haiku 4.5",
        "maker": "Anthropic",
        "tier": "paid",
        "source": "openrouter_haiku_run1.jsonl",
        "planned_attempts": 24,  # 24 instances x 1 repeat; stopped at 20 when the budget ran out
        "note": "Paid API via OpenRouter, one attempt per task, stopped when the $10 budget ran out.",
    },
    {
        "id": "ollama_chat/qwen2.5-coder:14b",
        "name": "Qwen2.5-Coder 14B",
        "maker": "Alibaba",
        "tier": "local",
        "source": "oss_leaderboard_run1.jsonl",
        "planned_attempts": 240,
        "note": "Local, free. All 240 planned attempts done.",
    },
    {
        "id": "ollama_chat/codestral:latest",
        "name": "Codestral 22B",
        "maker": "Mistral",
        "tier": "local",
        "source": "oss_leaderboard_run1.jsonl",
        "planned_attempts": 240,
        "note": "Local, free. All 240 planned attempts done.",
    },
    {
        "id": "ollama_chat/qwen3:14b",
        "name": "Qwen3 14B",
        "maker": "Alibaba",
        "tier": "local",
        "source": "oss_leaderboard_run1.jsonl",
        "planned_attempts": 240,
        "note": "Local, free. Stopped early: 167 of 240 attempts, so later tasks are under-sampled.",
    },
    {
        "id": "ollama_chat/gpt-oss:20b",
        "name": "gpt-oss 20B",
        "maker": "OpenAI",
        "tier": "local",
        "source": "oss_leaderboard_run1.jsonl",
        "planned_attempts": 240,
        "note": "Planned, never run. Shown so its absence is visible; it has no score.",
    },
]

# Smoke tests from task T8: a handful of calls made to check cost logging, not a benchmark run.
SMOKE_MODEL = "anthropic/claude-sonnet-4-5-20250929"


def wilson(resolved: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval. Unlike a +/- standard error it stays sensible at 0 of n."""
    if n == 0:
        return 0.0, 0.0
    p = resolved / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def read_rows(name: str) -> list[dict]:
    path = RESULTS / name
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def outcome_code(row: dict) -> int | None:
    """0 unresolved, 1 resolved, 2 timeout, 3 patch would not apply; None = excluded (infra)."""
    status = row["status"]
    if status == "infra_error":
        return None
    if status == "ok":
        return 1 if row["resolved"] else 0
    if status == "timeout":
        return 2
    if status == "patch_apply_failed":
        return 3
    return 0


def main() -> None:
    instances = [
        json.loads(line)
        for line in (ROOT / "datasets" / "instances.jsonl").read_text().splitlines()
        if line.strip()
    ]
    contamination = json.loads((ROOT / "datasets" / "contamination.json").read_text())
    instance_rows = []
    for inst in instances:
        iid = inst["instance_id"]
        instance_rows.append(
            {
                "id": iid,
                "repo": inst["repo"],
                "language": inst.get("language", "typescript"),
                "merge_date": contamination.get(iid, {}).get("pr_merge_date"),
                "fail_to_pass": len(inst["fail_to_pass"]),
                "pass_to_pass": len(inst["pass_to_pass"]),
            }
        )
    instance_rows.sort(key=lambda r: (r["language"], r["repo"], r["id"]))
    index_of = {r["id"]: i for i, r in enumerate(instance_rows)}

    raw = {name: read_rows(name) for name in {m["source"] for m in MODELS}}
    models_out, attempts = [], []
    for mi, m in enumerate(MODELS):
        rows = [r for r in raw[m["source"]] if r["model"] == m["id"]]
        counts = {0: 0, 1: 0, 2: 0, 3: 0}
        excluded = 0
        cost = 0.0
        covered = set()
        for r in rows:
            code = outcome_code(r)
            cost += r.get("cost_usd") or 0.0
            covered.add(r["instance_id"])
            if code is None:
                excluded += 1
                continue
            counts[code] += 1
            attempts.append([mi, index_of[r["instance_id"]], r.get("repeat", 0), code])
        n = sum(counts.values())
        resolved = counts[1]
        low, high = wilson(resolved, n)
        if n == 0:
            status = "not_run"
        elif n < m["planned_attempts"]:
            status = "partial"
        else:
            status = "complete"
        models_out.append(
            {
                "id": m["id"],
                "name": m["name"],
                "maker": m["maker"],
                "tier": m["tier"],
                "note": m["note"],
                "status": status,
                "attempts": n,
                "planned_attempts": m["planned_attempts"],
                "resolved": resolved,
                "unresolved": counts[0],
                "timeouts": counts[2],
                "patch_apply_failed": counts[3],
                "infra_excluded": excluded,
                "rate": resolved / n if n else None,
                "ci_low": low if n else None,
                "ci_high": high if n else None,
                "cost_usd": round(cost, 3),
                "cost_per_attempt": round(cost / n, 3) if n else None,
                "instances_covered": len(covered),
                "instances_total": len(instance_rows),
            }
        )

    smoke = [r for r in read_rows("real_smoke.jsonl") if r["model"] == SMOKE_MODEL]
    smoke_out = {
        "model": "Claude Sonnet 4.5",
        "attempts": len([r for r in smoke if r["status"] != "infra_error"]),
        "resolved": len([r for r in smoke if r["status"] == "ok" and r["resolved"]]),
        "cost_usd": round(sum(r.get("cost_usd") or 0 for r in smoke), 3),
    }

    languages: dict[str, int] = {}
    for r in instance_rows:
        languages[r["language"]] = languages.get(r["language"], 0) + 1

    total_attempts = sum(m["attempts"] for m in models_out)
    total_resolved = sum(m["resolved"] for m in models_out)
    out = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "dataset": {
            "version": DATASET_VERSION,
            "instances": len(instance_rows),
            "repos": len({r["repo"] for r in instance_rows}),
            "languages": languages,
        },
        "totals": {
            "attempts": total_attempts,
            "resolved": total_resolved,
            "models_with_data": len([m for m in models_out if m["attempts"]]),
            "cost_usd": round(sum(m["cost_usd"] for m in models_out), 2),
        },
        "models": models_out,
        "instances": instance_rows,
        # [model_index, instance_index, repeat, outcome_code]; codes: 0 unresolved, 1 resolved,
        # 2 timeout, 3 patch did not apply. Infra errors are excluded (see models[].infra_excluded).
        "attempts": attempts,
        "smoke_test": smoke_out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(
        f"wrote {OUT.relative_to(ROOT)}: {total_attempts} attempts, {total_resolved} resolved, "
        f"{OUT.stat().st_size / 1024:.0f} KB"
    )
    for m in models_out:
        print(f"  {m['name']:<20} {m['resolved']}/{m['attempts']} ({m['status']})  ${m['cost_usd']}")


if __name__ == "__main__":
    main()
