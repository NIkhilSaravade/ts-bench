from dataclasses import dataclass, field
from enum import StrEnum


class EvalStatus(StrEnum):
    OK = "ok"  # ran to completion -- check `resolved`
    PATCH_APPLY_FAILED = "patch_apply_failed"
    TEST_PATCH_APPLY_FAILED = "test_patch_apply_failed"
    TIMEOUT = "timeout"
    INFRA_ERROR = "infra_error"  # install crashed, runner produced no output, etc.


@dataclass
class EvalResult:
    instance_id: str
    status: EvalStatus
    resolved: bool = False  # only ever True when status == OK
    fail_to_pass_results: dict[str, bool] = field(default_factory=dict)
    pass_to_pass_results: dict[str, bool] = field(default_factory=dict)
    patch_strategy: str | None = None  # "strict" | "fuzzy" | "empty" | None
    reset_paths: list[str] = field(default_factory=list)
    wall_clock_seconds: float = 0.0
    stdout_tail: str = ""  # last ~2000 chars, for debugging
    stderr_tail: str = ""
    cost_usd: float | None = None  # None until T8 has a real agent to meter
    tokens_used: int | None = None
