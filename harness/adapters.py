"""T13: the one place `pipeline`/`harness` core code picks a LanguageAdapter
class by name. Everywhere else (evaluate()'s 7-step loop, validate.py's
red/green gate) stays completely language-agnostic -- this factory is the
single seam, not scattered `if language == ...` checks.
"""

from pathlib import Path

from harness.language_adapter import LanguageAdapter
from harness.python_adapter import PythonAdapter
from harness.ts_adapter import TypeScriptAdapter

_ADAPTERS: dict[str, type[LanguageAdapter]] = {
    "typescript": TypeScriptAdapter,
    "python": PythonAdapter,
}


def get_adapter(language: str, repo_path: Path, package_path: Path | None = None) -> LanguageAdapter:
    try:
        adapter_cls = _ADAPTERS[language]
    except KeyError:
        raise ValueError(f"no LanguageAdapter registered for language={language!r}") from None
    return adapter_cls(repo_path=repo_path, package_path=package_path)
