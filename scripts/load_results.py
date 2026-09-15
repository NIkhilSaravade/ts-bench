"""Step 7 follow-up: load real run-driver JSONL output into Postgres as
actual benchmark entries (models/runs/results), instead of leaving the
real leaderboard data sitting only in results/*.jsonl.

One `run_id` is created per (model, dataset_version, source_file) group --
consistent with a "run" being one evaluation session (T5's schema comment).
Every record's (run_id, instance_id, repeat) is inserted with
ON CONFLICT DO NOTHING, so this is safe to re-run against the same file.

Usage: uv run python scripts/load_results.py results/openrouter_haiku_run1.jsonl --dataset-version v0.2
"""

import argparse
import json
from pathlib import Path

from pipeline.db import connect

# Real, minimal provenance for every model this script has actually loaded --
# not guessed, filled in as each one was used against the real dataset.
KNOWN_MODELS = {
    "openrouter/anthropic/claude-haiku-4.5": {
        "provider": "openrouter",
        "notes": "Paid tier, real OpenRouter billing (T-step7).",
    },
    "openrouter/qwen/qwen3-coder-30b-a3b-instruct": {
        "provider": "openrouter",
        "notes": "Abandoned after a 0/3 pilot -- kept for the record.",
    },
    "ollama_chat/qwen2.5-coder:14b": {
        "provider": "ollama (local)",
        "notes": "Free tier, $0 cost, local inference.",
    },
    "ollama_chat/codestral:latest": {
        "provider": "ollama (local)",
        "notes": "Free tier, $0 cost, local inference.",
    },
    "ollama_chat/qwen3:14b": {
        "provider": "ollama (local)",
        "notes": "Free tier, $0 cost, local inference.",
    },
    "ollama_chat/gpt-oss:20b": {
        "provider": "ollama (local)",
        "notes": "Free tier, $0 cost, local inference.",
    },
}


def ensure_model(conn, model_id: str) -> None:
    info = KNOWN_MODELS.get(model_id, {})
    conn.execute(
        """
        INSERT INTO models (model_id, provider, notes)
        VALUES (%s, %s, %s)
        ON CONFLICT (model_id) DO NOTHING
        """,
        (model_id, info.get("provider"), info.get("notes")),
    )


def get_or_create_run(conn, model_id: str, dataset_version: str, source_file: str) -> int:
    row = conn.execute(
        """
        SELECT run_id FROM runs
        WHERE model_id = %s AND dataset_version = %s AND config->>'source_file' = %s
        """,
        (model_id, dataset_version, source_file),
    ).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        """
        INSERT INTO runs (model_id, dataset_version, scaffold_version, config)
        VALUES (%s, %s, %s, %s)
        RETURNING run_id
        """,
        (model_id, dataset_version, "agent/loop.py@step7", json.dumps({"source_file": source_file})),
    ).fetchone()
    return row[0]


def main():
    parser = argparse.ArgumentParser(
        description="Load a run_driver.py JSONL file into Postgres as real results."
    )
    parser.add_argument("jsonl_path")
    parser.add_argument("--dataset-version", default="v0.2")
    args = parser.parse_args()

    records = [json.loads(line) for line in Path(args.jsonl_path).read_text().splitlines() if line.strip()]
    models = sorted({r["model"] for r in records})

    conn = connect()
    for model_id in models:
        ensure_model(conn, model_id)

    run_ids: dict[str, int] = {
        model_id: get_or_create_run(conn, model_id, args.dataset_version, args.jsonl_path)
        for model_id in models
    }

    inserted = 0
    skipped = 0
    for r in records:
        run_id = run_ids[r["model"]]
        cur = conn.execute(
            """
            INSERT INTO results (
                run_id, instance_id, dataset_version, repeat, status, resolved,
                fail_to_pass_results, pass_to_pass_results, patch_strategy,
                wall_clock_seconds, stderr_tail, cost_usd, tokens_used
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id, instance_id, repeat) DO NOTHING
            """,
            (
                run_id,
                r["instance_id"],
                args.dataset_version,
                r.get("repeat", 0),
                r["status"],
                r["resolved"],
                json.dumps(r.get("fail_to_pass_results", {})),
                json.dumps(r.get("pass_to_pass_results", {})),
                r.get("patch_strategy"),
                r.get("wall_clock_seconds", 0),
                r.get("stderr_tail"),
                r.get("cost_usd"),
                r.get("tokens_used"),
            ),
        )
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    print(f"{args.jsonl_path}: {inserted} results inserted, {skipped} already present (skipped).")
    print(f"Runs: {run_ids}")


if __name__ == "__main__":
    main()
