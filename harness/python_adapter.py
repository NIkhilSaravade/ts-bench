"""T13: a second LanguageAdapter, proving the four-method seam from T2
generalizes beyond TypeScript.

Deliberately narrower in scope than TypeScriptAdapter for this first pass:
`pip`/`poetry`/`uv`/`pipenv` are all DETECTED, but only the `pip` path (a
`requirements.txt`, or a bare `pyproject.toml`/`setup.py` installed with
`pip install -e .`) has been live-verified end to end. Real repos mined for
this task all happened to be pip-based, so poetry/uv/pipenv installs are
implemented but unverified against a live repo -- the same honest caveat
T2's notes already applied to mocha.

Every install/test invocation runs inside a fresh, isolated venv created at
`<repo_path>/.tsbench-venv` -- necessary for real isolation, and desirable
anyway for the same reproducibility reasons TypeScriptAdapter pins an exact
node version rather than trusting whatever's ambient. Built with `uv venv`/
`uv pip install`, not the stdlib `venv` module: this environment's `python3
-m venv` is broken (`ensurepip` needs the `python3-venv` apt package, which
needs sudo we don't have) -- `uv` sidesteps that entirely and is already
this whole project's own toolchain, so it's not a new dependency to justify.
"""

import json
import tomllib
from pathlib import Path

from harness.language_adapter import Environment, LanguageAdapter

_VENV_DIRNAME = ".tsbench-venv"

# pytest's own documented exit codes (https://docs.pytest.org/en/stable/
# reference/exit-codes.html): 4 = USAGE_ERROR, which pytest also uses for a
# genuine collection-time failure (an import/syntax error in a test file or
# conftest.py) -- distinct from 1 (real test failures) and 5 (no tests
# collected, but the suite itself loaded fine). Unlike Java's Maven output
# (see java_adapter.py's JavaCompileFailure, added after a truncation bug),
# this needs no string-matching against captured output at all: pytest's
# exit code IS the classification, stable and immune to truncation by
# construction. Caught live: a real model patch introduced a syntax error
# (`_>` instead of `->` in a return-type annotation), which made pytest fail
# to even import the module at collection time -- a genuine "the agent's
# patch doesn't parse" failure, not an infra problem.
_PYTEST_USAGE_ERROR_EXIT_CODE = 4


class PythonCollectionFailure(RuntimeError):
    """pytest couldn't even collect tests -- a real, scoreable outcome (the
    candidate patch broke the module enough that it doesn't import/parse),
    not a genuine infra problem. See is_compile_failure()."""


class PythonAdapter(LanguageAdapter):
    def __init__(self, repo_path: Path, package_path: Path | None = None):
        self.repo_path = repo_path
        self.package_path = package_path or repo_path

    def detect_environment(self, repo_path: Path) -> Environment:
        manager = self._detect_package_manager(self.repo_path)
        version = self._detect_python_version(self.repo_path)
        return Environment(
            language_version=version,
            package_manager=manager,
            test_runner="pytest",
            install_cmd=self._install_cmd(manager),
            test_cmd_template=["pytest"],
        )

    def install(self, sandbox, env: Environment) -> None:
        venv_dir = self._venv_dir()
        result = sandbox.run(
            ["uv", "venv", str(venv_dir), "--python", env.language_version], cwd=self.repo_path
        )
        if result.returncode != 0:
            raise RuntimeError(f"venv creation failed:\n{result.stderr}")

        # setuptools-scm (a common choice for git-tag-derived __version__)
        # needs real git history to compute a version -- which every instance
        # deliberately doesn't have (materialize_instance() git-archives a
        # plain, git-free file tree, the same anti-leakage property T4
        # relies on). Without this, `pip install -e .`/`pip install .` on any
        # such package fails outright with "setuptools-scm was unable to
        # detect version" -- a real, structural incompatibility, not a repo
        # picking a "wrong" packaging tool. SETUPTOOLS_SCM_PRETEND_VERSION is
        # setuptools-scm's own documented escape hatch for exactly this case
        # (building from a source tree without git metadata).
        install_env = {"SETUPTOOLS_SCM_PRETEND_VERSION": "0.0.0"}
        result = sandbox.run(env.install_cmd, cwd=self.repo_path, timeout=600, extra_env=install_env)
        if result.returncode != 0:
            raise RuntimeError(f"install failed:\n{result.stderr}")

        # The repo's own test suite only ever needs to declare pytest as a
        # dev dependency, never pytest-json-report/pytest-cov -- those are
        # our reporter plus a common addopts dependency some repos' own
        # tox.ini/pytest.ini assume is already present, same relationship
        # TypeScriptAdapter has with vitest's --reporter=json flag.
        result = sandbox.run(
            self._uv_pip_install("pytest", "pytest-json-report", "pytest-cov"), cwd=self.repo_path
        )
        if result.returncode != 0:
            raise RuntimeError(f"pytest-json-report install failed:\n{result.stderr}")

    def run_tests(
        self, sandbox, env: Environment, test_ids: list[str] | None = None, timeout: int = 300
    ) -> str:
        pytest_bin = str(self._venv_bin("pytest"))
        output_file = self.package_path / "pytest-report.json"
        cmd = [
            pytest_bin,
            "--json-report",
            f"--json-report-file={output_file.name}",
            "-p",
            "no:cacheprovider",
        ]
        if test_ids:
            cmd += test_ids
        result = sandbox.run(cmd, cwd=self.package_path, timeout=timeout)

        if not output_file.exists():
            message = f"pytest produced no output file (exit {result.returncode}).\nstderr:\n{result.stderr}"
            if result.returncode == _PYTEST_USAGE_ERROR_EXIT_CODE:
                raise PythonCollectionFailure(message)
            raise RuntimeError(message)
        return output_file.read_text()

    def parse_results(self, raw_output: str, runner: str = "pytest") -> dict[str, bool]:
        data = json.loads(raw_output)
        # pytest's own nodeid ("path/to/test_foo.py::test_bar") is already
        # exactly the canonical "{rel_path}::{name}" shape every other
        # adapter has to construct by hand -- nothing to build here.
        return {t["nodeid"]: t["outcome"] == "passed" for t in data.get("tests", [])}

    def is_compile_failure(self, error: Exception) -> bool:
        return isinstance(error, PythonCollectionFailure)

    # --- private helpers ---

    def _venv_dir(self) -> Path:
        return self.repo_path / _VENV_DIRNAME

    def _venv_bin(self, name: str) -> Path:
        return self._venv_dir() / "bin" / name

    def _uv_pip_install(self, *packages: str) -> list[str]:
        return ["uv", "pip", "install", "--python", str(self._venv_bin("python")), *packages]

    def _install_cmd(self, manager: str) -> list[str]:
        editable_target = f".[{extra}]" if (extra := self._detect_test_extra()) else "."
        if manager == "pip":
            if (self.repo_path / "requirements.txt").exists():
                return self._uv_pip_install("-r", "requirements.txt")
            return self._uv_pip_install("-e", editable_target)
        if manager == "poetry":
            return self._uv_pip_install(editable_target)
        if manager == "uv":
            if (self.repo_path / "requirements.txt").exists():
                return self._uv_pip_install("-r", "requirements.txt")
            return self._uv_pip_install(editable_target)
        if manager == "pipenv":
            return self._uv_pip_install("-e", editable_target)
        raise ValueError(f"Unknown package manager: {manager}")

    def _detect_test_extra(self) -> str | None:
        """A `pyproject.toml`-declared PEP 621 optional-dependencies group
        that plausibly holds test deps (pytest, its plugins, and whatever
        the test suite itself imports -- e.g. arrow's tests import `pytz`,
        declared only in its `test` extra, never in the base package deps).
        Without this, `pip install -e .` alone installs a package that
        imports fine but whose OWN test suite can't even be collected."""
        pyproject = self.repo_path / "pyproject.toml"
        if not pyproject.exists():
            return None
        try:
            data = tomllib.loads(pyproject.read_text())
        except tomllib.TOMLDecodeError:
            return None
        extras = data.get("project", {}).get("optional-dependencies", {})
        for name in ("test", "tests", "testing", "dev"):
            if name in extras:
                return name
        return None

    def _detect_package_manager(self, repo_path: Path) -> str:
        if (repo_path / "uv.lock").exists():
            return "uv"
        if (repo_path / "poetry.lock").exists():
            return "poetry"
        if (repo_path / "Pipfile.lock").exists():
            return "pipenv"
        if any((repo_path / f).exists() for f in ("requirements.txt", "pyproject.toml", "setup.py")):
            return "pip"
        raise ValueError(f"No recognizable Python dependency manifest in {repo_path}")

    def _detect_python_version(self, repo_path: Path, default: str = "3.12") -> str:
        f = repo_path / ".python-version"
        if f.exists():
            v = f.read_text().strip()
            if v:
                return v
        return default
