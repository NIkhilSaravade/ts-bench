import json

import pytest

from pipeline.dataset_export import export_version


def _write_minimal_instance(path, instance_id="acme__widget-1"):
    instance = {
        "instance_id": instance_id,
        "repo": "acme/widget",
        "base_commit": "a" * 40,
        "problem_statement": "it's broken",
        "gold_patch": "diff --git a/x b/x\n",
        "test_patch": "diff --git a/x.test.ts b/x.test.ts\n",
        "fail_to_pass": ["x.test.ts::works"],
        "pass_to_pass": [],
        "environment": {
            "node_version": "20.11.1",
            "package_manager": "npm",
            "install_cmd": "npm ci",
            "test_cmd": "npm test",
        },
    }
    path.write_text(json.dumps(instance) + "\n")


def test_export_writes_instances_and_info(tmp_path):
    instances_file = tmp_path / "instances.jsonl"
    _write_minimal_instance(instances_file)
    versions_dir = tmp_path / "versions"

    out_dir = export_version(
        "v0.1",
        "test version",
        instances_file=instances_file,
        contamination_file=tmp_path / "missing_contamination.json",
        versions_dir=versions_dir,
    )

    rows = [json.loads(line) for line in (out_dir / "instances.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["instance_id"] == "acme__widget-1"
    assert rows[0]["head_commit"] is None  # no contamination file -- graceful, not a crash

    info = json.loads((out_dir / "dataset_info.json").read_text())
    assert info["version"] == "v0.1"
    assert info["instance_count"] == 1
    assert info["repos"] == ["acme/widget"]


def test_export_merges_contamination_metadata(tmp_path):
    instances_file = tmp_path / "instances.jsonl"
    _write_minimal_instance(instances_file)
    contamination_file = tmp_path / "contamination.json"
    contamination_file.write_text(
        json.dumps({"acme__widget-1": {"head_commit": "b" * 40, "pr_merge_date": "2024-01-01"}})
    )

    out_dir = export_version(
        "v0.1",
        "test version",
        instances_file=instances_file,
        contamination_file=contamination_file,
        versions_dir=tmp_path / "versions",
    )

    row = json.loads((out_dir / "instances.jsonl").read_text().splitlines()[0])
    assert row["pr_merge_date"] == "2024-01-01"
    assert row["head_commit"] == "b" * 40


def test_export_refuses_to_overwrite_published_version(tmp_path):
    instances_file = tmp_path / "instances.jsonl"
    _write_minimal_instance(instances_file)
    versions_dir = tmp_path / "versions"

    export_version("v0.1", "first", instances_file=instances_file, versions_dir=versions_dir)
    with pytest.raises(FileExistsError):
        export_version("v0.1", "second", instances_file=instances_file, versions_dir=versions_dir)
