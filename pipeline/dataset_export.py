"""T5: export the validated dataset as a versioned, immutable snapshot.

A published version is never overwritten -- scores are only comparable
against a fixed task set, so "ts-bench v0.1" must mean one exact set
forever. Re-running the exporter with the same version on a changed
dataset is refused; give a new version instead.

The export is plain JSONL, which is exactly the format HuggingFace's
`datasets` library loads directly (`load_dataset("json", data_files=...)`)
-- no separate "convert to a HF dataset" step is needed. Actually pushing
it to the HF Hub is T10's job (its own Build section says so explicitly),
once there's a final dataset worth publishing publicly.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from pipeline.schema import TaskInstance

ROOT = Path.home() / "projects" / "ts-bench"
INSTANCES_FILE = ROOT / "datasets" / "instances.jsonl"
CONTAMINATION_FILE = ROOT / "datasets" / "contamination.json"
VERSIONS_DIR = ROOT / "datasets" / "versions"


def load_instances(instances_file: Path = INSTANCES_FILE) -> list[TaskInstance]:
    with open(instances_file) as f:
        return [TaskInstance.model_validate_json(line) for line in f if line.strip()]


def load_contamination(contamination_file: Path = CONTAMINATION_FILE) -> dict:
    if not contamination_file.exists():
        return {}
    return json.loads(contamination_file.read_text())


def export_version(
    version: str,
    description: str,
    instances_file: Path = INSTANCES_FILE,
    contamination_file: Path = CONTAMINATION_FILE,
    versions_dir: Path = VERSIONS_DIR,
) -> Path:
    """Write datasets/versions/<version>/instances.jsonl + dataset_info.json.
    Refuses to overwrite an already-published version -- immutability is the
    whole point (see module docstring)."""
    out_dir = versions_dir / version
    if out_dir.exists():
        raise FileExistsError(
            f"{out_dir} already exists -- dataset versions are immutable once published. "
            "Use a new version string if the underlying dataset changed."
        )

    instances = load_instances(instances_file)
    contamination = load_contamination(contamination_file)

    out_dir.mkdir(parents=True)
    with open(out_dir / "instances.jsonl", "w") as f:
        for inst in instances:
            row = json.loads(inst.model_dump_json())
            meta = contamination.get(inst.instance_id, {})
            row["head_commit"] = meta.get("head_commit")
            row["pr_merge_date"] = meta.get("pr_merge_date")
            f.write(json.dumps(row) + "\n")

    info = {
        "version": version,
        "description": description,
        "created_at": datetime.now(UTC).isoformat(),
        "instance_count": len(instances),
        "repos": sorted({inst.repo for inst in instances}),
    }
    (out_dir / "dataset_info.json").write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")
    return out_dir
