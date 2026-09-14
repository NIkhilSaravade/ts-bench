"""T15: enqueue a (model, instance_id, repeat) job matrix onto Kafka, the
same key run_driver.py already uses for JSONL resumability (T9) -- workers
just consume this topic instead of a driver looping over a Python list.

Usage:
    uv run python scripts/kafka_produce_jobs.py <run_id> <dataset_version> \
        <model> <instance_id1,instance_id2,...> <repeats>
"""

import json
import os
import sys

from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

# No port is published to the host -- the broker only has an address on the
# "kind" docker network (172.18.0.10), which the WSL host can also reach
# directly (native WSL2 dockerd routes container IPs, no -p needed), the
# same reachability T5's Postgres round-trip already relied on.
KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "172.18.0.10:9092")
TOPIC = "ts-bench-jobs"
PARTITIONS = 6  # more than any realistic worker-replica count in this demo


def ensure_topic(broker: str, topic: str, partitions: int) -> None:
    admin = KafkaAdminClient(bootstrap_servers=broker)
    try:
        admin.create_topics([NewTopic(name=topic, num_partitions=partitions, replication_factor=1)])
        print(f"created topic {topic!r} with {partitions} partitions")
    except TopicAlreadyExistsError:
        print(f"topic {topic!r} already exists")
    finally:
        admin.close()


def main() -> None:
    if len(sys.argv) != 6:
        print(
            "usage: kafka_produce_jobs.py <run_id> <dataset_version> <model> "
            "<instance_id1,instance_id2,...> <repeats>",
            file=sys.stderr,
        )
        sys.exit(1)

    run_id = int(sys.argv[1])
    dataset_version = sys.argv[2]
    model = sys.argv[3]
    instance_ids = [s for s in sys.argv[4].split(",") if s]
    repeats = int(sys.argv[5])

    ensure_topic(KAFKA_BROKER, TOPIC, PARTITIONS)

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BROKER,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
    )

    count = 0
    for instance_id in instance_ids:
        for repeat in range(repeats):
            job = {
                "run_id": run_id,
                "dataset_version": dataset_version,
                "model": model,
                "instance_id": instance_id,
                "repeat": repeat,
            }
            # The (instance_id, repeat) key is the same idempotency key
            # run_driver.py's JSONL resumability already uses (T9) -- keying
            # by it also gives every repeat of the same instance the same
            # partition, a harmless, not load-bearing affinity choice.
            producer.send(TOPIC, key=f"{instance_id}:{repeat}", value=job)
            count += 1
    producer.flush()
    producer.close()
    print(f"enqueued {count} jobs onto {TOPIC!r}")


if __name__ == "__main__":
    main()
