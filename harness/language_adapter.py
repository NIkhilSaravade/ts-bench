from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Environment:
    """Everything language-specific about ONE repo, computed once."""

    language_version: str  # e.g. "20.11.1" (exact, never "latest")
    package_manager: str  # "npm" | "pnpm" | "yarn"
    test_runner: str  # "vitest" | "jest" | "mocha"
    install_cmd: list[str]  # e.g. ["pnpm", "install", "--frozen-lockfile"]
    test_cmd_template: list[str]  # placeholders filled in by run_tests


class LanguageAdapter(ABC):
    @abstractmethod
    def detect_environment(self, repo_path: Path) -> Environment:
        """Inspect the checked-out repo and return what it needs to run."""

    @abstractmethod
    def install(self, sandbox, env: Environment) -> None:
        """Get dependencies installed reproducibly inside the sandbox."""

    @abstractmethod
    def run_tests(
        self,
        sandbox,
        env: Environment,
        test_ids: list[str] | None = None,
        timeout: int = 300,
    ) -> str:
        """Execute tests (all, or only test_ids) and return raw runner output."""

    @abstractmethod
    def parse_results(self, raw_output: str) -> dict[str, bool]:
        """Map runner output to a stable {test_id: pass_bool} dict."""

    def is_compile_failure(self, error: Exception) -> bool:
        """Whether `error` (raised by install()/run_tests()) is a
        compile-time failure specifically, as opposed to any other kind of
        infra problem (network, timeout, misconfiguration).

        Default False -- meaningful only for compiled-language adapters.
        Enables the "salvage" path in pipeline.validate.red_run (T14's
        finding): when a candidate's pre-fix code plus its new/changed
        tests won't even compile, that's the bug being real in its most
        extreme form, not a reason to discard the candidate outright. A
        dynamically-typed adapter's own test runner already reports real
        pass/fail for a brand-new test without needing this at all, so the
        base implementation is correct for every existing adapter.
        """
        return False

    def extract_test_ids_from_diff(self, diff_text: str) -> list[str]:
        """Best-effort: pull the test IDs a test-only diff touches, without
        running anything. Only ever called when is_compile_failure() was
        True for the error that triggered it. Default empty -- "nothing to
        salvage" -- so the original reject-on-exception behavior is
        preserved for every adapter that doesn't override this.
        """
        return []
