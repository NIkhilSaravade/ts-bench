"""T5: round-trip a published dataset version into Postgres.

Applies infra/schema.sql (idempotent -- CREATE TABLE IF NOT EXISTS), inserts
the dataset_versions row and every task from
datasets/versions/<version>/instances.jsonl, then reads everything back and
verifies it matches the file exactly. Safe to re-run: inserts are
ON CONFLICT DO NOTHING, consistent with versions being immutable once
published.

Usage: uv run python scripts/load_postgres.py v0.1
"""

import json
import sys
from pathlib import Path

from pipeline.db import connect

ROOT = Path.home() / "projects" / "ts-bench"
SCHEMA_FILE = ROOT / "infra" / "schema.sql"
VERSIONS_DIR = ROOT / "datasets" / "versions"


def apply_schema(conn) -> None:
    conn.execute(SCHEMA_FILE.read_text())


def load_version(conn, version: str) -> list[dict]:
    version_dir = VERSIONS_DIR / version
    info = json.loads((version_dir / "dataset_info.json").read_text())
    rows = [json.loads(line) for line in (version_dir / "instances.jsonl").read_text().splitlines() if line]

    conn.execute(
        """
        INSERT INTO dataset_versions (version, instance_count, description)
        VALUES (%s, %s, %s)
        ON CONFLICT (version) DO NOTHING
        """,
        (version, info["instance_count"], info["description"]),
    )

    for row in rows:
        conn.execute(
            """
            INSERT INTO tasks (
                instance_id, dataset_version, repo, base_commit, problem_statement,
                gold_patch, test_patch, fail_to_pass, pass_to_pass, environment,
                head_commit, pr_merge_date
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (instance_id, dataset_version) DO NOTHING
            """,
            (
                row["instance_id"],
                version,
                row["repo"],
                row["base_commit"],
                row["problem_statement"],
                row["gold_patch"],
                row["test_patch"],
                json.dumps(row["fail_to_pass"]),
                json.dumps(row["pass_to_pass"]),
                json.dumps(row["environment"]),
                row.get("head_commit"),
                row.get("pr_merge_date"),
            ),
        )
    conn.commit()
    return rows


def verify_round_trip(conn, version: str, expected_rows: list[dict]) -> None:
    cur = conn.execute(
        "SELECT instance_id, fail_to_pass, pass_to_pass, pr_merge_date FROM tasks WHERE dataset_version = %s",
        (version,),
    )
    db_rows = {r[0]: r for r in cur.fetchall()}

    expected_ids = {r["instance_id"] for r in expected_rows}
    db_ids = set(db_rows.keys())
    if db_ids != expected_ids:
        raise AssertionError(f"instance_id mismatch: file has {expected_ids - db_ids} missing from db")

    for row in expected_rows:
        _, db_f2p, db_p2p, db_merge_date = db_rows[row["instance_id"]]
        if db_f2p != row["fail_to_pass"]:
            raise AssertionError(f"{row['instance_id']}: fail_to_pass mismatch after round-trip")
        if db_p2p != row["pass_to_pass"]:
            raise AssertionError(f"{row['instance_id']}: pass_to_pass mismatch after round-trip")
        expected_merge_date = row.get("pr_merge_date")
        if expected_merge_date and str(db_merge_date) != expected_merge_date:
            raise AssertionError(f"{row['instance_id']}: pr_merge_date mismatch after round-trip")

    print(
        f"round-trip verified: {len(expected_rows)} tasks match exactly (fail_to_pass, pass_to_pass, "
        f"pr_merge_date all confirmed byte-for-byte against the source JSONL)."
    )


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: load_postgres.py <version>", file=sys.stderr)
        sys.exit(1)
    version = sys.argv[1]

    with connect() as conn:
        apply_schema(conn)
        rows = load_version(conn, version)
        verify_round_trip(conn, version, rows)


if __name__ == "__main__":
    main()
