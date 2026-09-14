"""The TaskInstance schema — the contract every later TS-Bench stage reads and writes.

A TaskInstance is a claim of the form: "at this exact commit, in this repo,
these named tests fail; applying this patch makes them pass, without breaking
these other named tests." Every field exists to make that claim checkable by
a machine, not just plausible to a human.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator

# A git commit SHA is a hex string. Git accepts abbreviated SHAs (7+ chars)
# but we pin to full 40-char SHAs here: an abbreviated SHA can become
# ambiguous as a repo grows new commits, and "reproducible forever" is the
# whole point of a benchmark task set.
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class Environment(BaseModel):
    """Everything needed to stand up the repo and run its tests.

    This is deliberately its own nested model rather than four loose fields
    on TaskInstance: it's a cohesive unit (you always need all four together
    to run a test). Record-keeping/documentation only -- eval_runner.py
    always calls the adapter's own detect_environment() fresh rather than
    trusting this, so nothing here needs to be executable, just accurate.

    `runtime_version` was originally named `node_version` -- fine while
    TypeScriptAdapter was the only implementation, but a real interface leak
    once T13 needed to record a Python interpreter version in it. Renamed
    once a second language actually existed to prove the leak, rather than
    guessing at the "right" generic name up front.
    """

    runtime_version: str = Field(
        ..., description="Pinned language runtime version, e.g. '20.11.0' or '3.12.1' -- not a range."
    )
    package_manager: str = Field(..., description="Which package manager was used to install dependencies.")
    install_cmd: str = Field(..., description="Exact command to install dependencies.")
    test_cmd: str = Field(..., description="Exact command to run the test suite.")

    @field_validator("package_manager")
    @classmethod
    def package_manager_is_known(cls, v: str) -> str:
        allowed = {"npm", "pnpm", "yarn", "pip", "poetry", "uv", "pipenv", "maven", "gradle"}
        if v not in allowed:
            raise ValueError(f"package_manager must be one of {allowed}, got {v!r}")
        return v


class TaskInstance(BaseModel):
    """One benchmark task: a repo frozen at a buggy commit, plus the answer key."""

    instance_id: str = Field(
        ..., description="Unique id, e.g. 'colinhacks__zod-1234' (<org>__<repo>-<pr_number>)."
    )
    repo: str = Field(..., description="GitHub 'owner/name', e.g. 'colinhacks/zod'.")
    base_commit: str = Field(..., description="Full 40-char commit SHA the task starts from.")
    problem_statement: str = Field(..., description="The issue text the agent is shown as the task.")
    gold_patch: str = Field(..., description="Unified diff of the human fix. Never shown to the agent.")
    test_patch: str = Field(
        ..., description="Unified diff adding/modifying the proving tests; applied after the agent's."
    )
    fail_to_pass: list[str] = Field(
        ..., description="Test IDs that fail at base_commit and must pass after a correct fix."
    )
    pass_to_pass: list[str] = Field(
        default_factory=list,
        description="Test IDs already passing at base_commit that must stay passing (regression guard)",
    )
    environment: Environment
    language: str = Field(
        default="typescript",
        description="Which LanguageAdapter this instance runs under -- selects the adapter, "
        "core pipeline/harness code never branches on it directly.",
    )

    @field_validator("language")
    @classmethod
    def language_is_known(cls, v: str) -> str:
        allowed = {"typescript", "python", "java"}
        if v not in allowed:
            raise ValueError(f"language must be one of {allowed}, got {v!r}")
        return v

    @field_validator("base_commit")
    @classmethod
    def base_commit_is_a_full_sha(cls, v: str) -> str:
        if not _GIT_SHA_RE.match(v):
            raise ValueError(f"base_commit must be a 40-character hex SHA, got {v!r}")
        return v

    @field_validator("repo")
    @classmethod
    def repo_is_owner_slash_name(cls, v: str) -> str:
        if v.count("/") != 1 or v.startswith("/") or v.endswith("/"):
            raise ValueError(f"repo must look like 'owner/name', got {v!r}")
        return v

    @model_validator(mode="after")
    def must_have_at_least_one_fail_to_pass(self) -> TaskInstance:
        # This is the actual definition of a benchmark task: if nothing was
        # failing before the fix, there was no bug, and "resolving" this
        # instance would mean nothing. This check encodes that definition
        # in code instead of leaving it as a comment someone can ignore.
        if len(self.fail_to_pass) == 0:
            raise ValueError(
                "fail_to_pass must contain at least one test — a task with no "
                "failing test at base_commit isn't a task, it's a no-op."
            )
        return self
