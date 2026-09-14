"""T15: a consumer-group worker. Runs as a K8s pod (see infra/k8s/), reads
one (model, instance_id, repeat) job at a time off Kafka, and produces
exactly the same EvalResult scripts/run_driver.py's sequential loop would
-- just pulled from a shared queue instead of a shared Python list, so
horizontally scaling out is "add more replicas," not "shard the list
yourself."

Idempotency: a (run_id, instance_id, repeat) row is written to Postgres at
most once (the same UNIQUE constraint infra/schema.sql already declares on
results). The Kafka offset for a job is committed only AFTER that write is
durably attempted -- so a worker that dies mid-job leaves its offset
uncommitted, Kafka redelivers the job to a surviving consumer in the group
after rebalancing, and the idempotent write makes that redelivery a safe
no-op if the first attempt actually did finish, or a normal retry if it
didn't. Either way: no lost result, no duplicate row.
"""

import json
import os
import socket
from pathlib import Path

from kafka import KafkaConsumer

from harness.driver import run_and_evaluate
from pipeline.db import connect
from pipeline.schema import TaskInstance

KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "172.18.0.10:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "ts-bench-jobs")
GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "ts-bench-workers")
MIRRORS_DIR = Path(os.environ.get("MIRRORS_DIR", "/app/mirrors"))
INSTANCES_FILE = Path(os.environ.get("INSTANCES_FILE", "/app/datasets/instances.jsonl"))

WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"


def load_instances() -> dict[str, TaskInstance]:
    out: dict[str, TaskInstance] = {}
    with open(INSTANCES_FILE) as f:
        for line in f:
            if not line.strip():
                continue
            instance = TaskInstance.model_validate_json(line)
            out[instance.instance_id] = instance
    return out


def already_done(conn, run_id: int, instance_id: str, repeat: int) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM results WHERE run_id = %s AND instance_id = %s AND repeat = %s",
        (run_id, instance_id, repeat),
    )
    return cur.fetchone() is not None


def write_result(conn, run_id: int, dataset_version: str, instance_id: str, repeat: int, result) -> None:
    conn.execute(
        """
        INSERT INTO results (
            run_id, instance_id, dataset_version, repeat, status, resolved,
            fail_to_pass_results, pass_to_pass_results, patch_strategy,
            reset_paths, wall_clock_seconds, stdout_tail, stderr_tail,
            cost_usd, tokens_used
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (run_id, instance_id, repeat) DO NOTHING
        """,
        (
            run_id,
            instance_id,
            dataset_version,
            repeat,
            result.status.value,
            result.resolved,
            json.dumps(result.fail_to_pass_results),
            json.dumps(result.pass_to_pass_results),
            result.patch_strategy,
            json.dumps(result.reset_paths),
            result.wall_clock_seconds,
            result.stdout_tail,
            result.stderr_tail,
            result.cost_usd,
            result.tokens_used,
        ),
    )
    conn.commit()


def main() -> None:
    instances = load_instances()
    print(f"[{WORKER_ID}] loaded {len(instances)} instances; connecting to {KAFKA_BROKER} ...", flush=True)

    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=KAFKA_BROKER,
        group_id=GROUP_ID,
        enable_auto_commit=False,  # commit only after a durable write -- see module docstring
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    conn = connect()

    print(f"[{WORKER_ID}] ready, consuming {TOPIC!r} as group {GROUP_ID!r} ...", flush=True)
    for message in consumer:
        job = message.value
        run_id, dataset_version = job["run_id"], job["dataset_version"]
        model, instance_id, repeat = job["model"], job["instance_id"], job["repeat"]

        if already_done(conn, run_id, instance_id, repeat):
            print(f"[{WORKER_ID}] SKIP (already recorded) {instance_id} repeat={repeat}", flush=True)
            consumer.commit()
            continue

        print(f"[{WORKER_ID}] START {instance_id} repeat={repeat} model={model}", flush=True)
        instance = instances[instance_id]
        result = run_and_evaluate(model, instance, MIRRORS_DIR)
        write_result(conn, run_id, dataset_version, instance_id, repeat, result)
        consumer.commit()
        print(
            f"[{WORKER_ID}] DONE  {instance_id} repeat={repeat} "
            f"status={result.status.value} resolved={result.resolved}",
            flush=True,
        )


if __name__ == "__main__":
    main()
