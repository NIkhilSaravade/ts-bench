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
