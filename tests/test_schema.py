import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.schema import TaskInstance

EXAMPLES_DIR = Path(__file__).parent.parent / "datasets" / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text())


def test_valid_instance_validates():
    instance = TaskInstance.model_validate(load_example("valid_instance.json"))
    assert instance.instance_id == "colinhacks__zod-1234"
    assert len(instance.fail_to_pass) == 1


def test_malformed_instance_is_rejected_with_the_right_reasons():
    with pytest.raises(ValidationError) as exc_info:
        TaskInstance.model_validate(load_example("malformed_instance.json"))

    # Assert on *which* checks fired, not just that something failed —
    # otherwise this test would keep passing even if we broke a different
    # validator and the field-level check we actually care about here went
    # silently unenforced.
    error_fields = {tuple(e["loc"]) for e in exc_info.value.errors()}
    assert ("base_commit",) in error_fields
    assert ("environment", "package_manager") in error_fields


def test_empty_fail_to_pass_is_rejected():
    # A structurally valid instance can still be semantically meaningless:
    # this is the model-level (not field-level) rule that a task must have
    # at least one failing test at base_commit, or it isn't a bug at all.
    data = load_example("valid_instance.json")
    data["fail_to_pass"] = []

    with pytest.raises(ValidationError, match="fail_to_pass must contain at least one test"):
        TaskInstance.model_validate(data)
