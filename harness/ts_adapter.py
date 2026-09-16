# harness/ts_adapter.py
import json
import os
import subprocess
from pathlib import Path

from harness.language_adapter import Environment, LanguageAdapter

_RUNNER_DEPS = {"vitest": "vitest", "jest": "jest", "mocha": "mocha"}
_RUNNER_CONFIGS = {
    "vitest": ["vitest.config.ts", "vitest.config.js", "vitest.config.mts"],
    "jest": ["jest.config.js", "jest.config.ts", "jest.config.cjs"],
    "mocha": [".mocharc.js", ".mocharc.json", ".mocharc.yml"],
}
_INSTALL_CMDS = {
    "npm": ["npm", "ci"],
    "pnpm": ["pnpm", "install", "--frozen-lockfile"],
    "yarn": ["yarn", "install", "--frozen-lockfile"],
}
_KNOWN_MANAGERS = {"npm", "pnpm", "yarn"}


class TypeScriptAdapter(LanguageAdapter):
    def __init__(self, repo_path: Path, package_path: Path | None = None):
        self.repo_path = repo_path
        # Defaults to repo_path for single-package repos -- zero behavior
        # change for zod/class-validator. Set explicitly for a monorepo
        # to scope test runner detection and test execution to one package,
        # while package manager / node version stay resolved from the root.
        self.package_path = package_path or repo_path
        self._pinned_env_cache: dict[str, dict[str, str]] = {}

    def detect_environment(self, repo_path: Path) -> Environment:
        manager, _pinned = self._detect_package_manager(self.repo_path)
        node_version = self._detect_node_version(self.repo_path)
        runner = self._detect_test_runner_with_fallback(self.package_path, self.repo_path)
        return Environment(
            language_version=node_version,
            package_manager=manager,
            test_runner=runner,
            install_cmd=_INSTALL_CMDS[manager],
            # A representative human-readable command, not necessarily
            # byte-identical to _build_test_cmd()'s actual reporter-flag-laden
            # invocation -- this only ever feeds the schema's documentation-only
            # Environment.test_cmd field (see pipeline/validate.py).
            test_cmd_template=[manager, "test"],
        )

    def install(self, sandbox, env: Environment) -> None:
        self._sanitize_package_manager_field(self.repo_path)
        self._sanitize_lifecycle_scripts(self.repo_path)
        extra_env = self._pinned_env(env.language_version)

        result = sandbox.run(env.install_cmd, cwd=self.repo_path, extra_env=extra_env)
        if result.returncode != 0 and "ERR_PNPM_IGNORED_BUILDS" in result.stderr:
            sandbox.run(["pnpm", "approve-builds", "--all"], cwd=self.repo_path, extra_env=extra_env)
            result = sandbox.run(env.install_cmd, cwd=self.repo_path, extra_env=extra_env)

        if result.returncode != 0:
            raise RuntimeError(f"install failed:\n{result.stderr}")

    def run_tests(
        self, sandbox, env: Environment, test_ids: list[str] | None = None, timeout: int = 300
    ) -> str:
        cmd = self._build_test_cmd(env.test_runner, test_ids)
        extra_env = self._pinned_env(env.language_version)
        result = sandbox.run(cmd, cwd=self.package_path, timeout=timeout, extra_env=extra_env)

        output_filename = "jest-results.json" if env.test_runner == "jest" else "vitest-results.json"
        output_file = self.package_path / output_filename
        if not output_file.exists():
            raise RuntimeError(
                f"{env.test_runner} produced no output file (exit {result.returncode}).\n"
                f"stderr:\n{result.stderr}"
            )
        return output_file.read_text()

    def parse_results(self, raw_output: str, runner: str) -> dict[str, bool]:
        data = json.loads(raw_output)

        if runner in ("jest", "vitest"):
            out: dict[str, bool] = {}
            for file_result in data["testResults"]:
                rel_path = str(Path(file_result["name"]).relative_to(self.repo_path))
                for a in file_result["assertionResults"]:
                    name = " > ".join([*a["ancestorTitles"], a["title"]])
                    out[f"{rel_path}::{name}"] = a["status"] == "passed"
            return out

        if runner == "mocha":
            out = {}
            for t in data.get("passes", []):
                rel_path = str(Path(t["file"]).relative_to(self.repo_path))
                out[f"{rel_path}::{t['fullTitle']}"] = True
            for t in data.get("failures", []):
                rel_path = str(Path(t["file"]).relative_to(self.repo_path))
                out[f"{rel_path}::{t['fullTitle']}"] = False
            return out

        raise ValueError(f"Unknown runner: {runner}")

    # --- private helpers ---

    def _detect_package_manager(self, repo_path: Path) -> tuple[str, str | None]:
        pkg_json = repo_path / "package.json"
        if pkg_json.exists():
            data = json.loads(pkg_json.read_text())
            pm_field = data.get("packageManager")
            if pm_field:
                name, _, version = pm_field.partition("@")
                if name in _KNOWN_MANAGERS:
                    return name, version or None

        candidates = [
            ("pnpm", repo_path / "pnpm-lock.yaml"),
            ("yarn", repo_path / "yarn.lock"),
            ("npm", repo_path / "package-lock.json"),
        ]
        existing = [(name, p) for name, p in candidates if p.exists()]
        if not existing:
            raise ValueError(f"No lockfile or recognized packageManager field found in {repo_path}")
        if len(existing) > 1:
            existing.sort(key=lambda t: t[1].stat().st_mtime, reverse=True)
        return existing[0][0], None

    def _sanitize_package_manager_field(self, repo_path: Path) -> None:
        pkg_json = repo_path / "package.json"
        if not pkg_json.exists():
            return
        data = json.loads(pkg_json.read_text())
        pm_field = data.get("packageManager", "")
        name = pm_field.partition("@")[0]
        if pm_field and name not in _KNOWN_MANAGERS:
            data.pop("packageManager")
            pkg_json.write_text(json.dumps(data, indent=2))

    def _sanitize_lifecycle_scripts(self, repo_path: Path) -> None:
        pkg_json = repo_path / "package.json"
        if not pkg_json.exists():
            return
        data = json.loads(pkg_json.read_text())
        scripts = data.get("scripts", {})
        changed = False
        for hook in ("prepare", "preinstall", "postinstall"):
            if hook in scripts:
                del scripts[hook]
                changed = True
        if changed:
            pkg_json.write_text(json.dumps(data, indent=2))

    def _pinned_env(self, version: str) -> dict[str, str]:
        """PATH override so install/test subprocesses run under the repo's
        OWN pinned node version, not whatever the ambient shell's nvm default
        happens to be.

        detect_environment() has always recorded node_version as metadata,
        but nothing previously used it to actually switch node -- every
        subprocess just ran under the ambient default. That stayed invisible
        while the default and every mined repo's pin were close enough (e.g.
        zod's default-pinned "20.11.1" against an ambient v20/v22), but broke
        outright once the ambient default moved to v24 and a repo pinned to
        v22 hit a real cross-version undici/AbortSignal incompatibility
        (`RequestInit: Expected signal ... to be an instance of AbortSignal`)
        that has nothing to do with the candidate's actual fix. Caching this
        per (adapter instance, version) matters because install() and every
        run_tests() call (repeated N times for flake detection) would
        otherwise re-invoke nvm/corepack every single time.
        """
        if version not in self._pinned_env_cache:
            self._pinned_env_cache[version] = {
                "PATH": f"{self._node_bin_dir(version)}:{os.environ['PATH']}",
                # A host nvm PATH means nothing inside a container -- this
                # plain, sandbox-agnostic hint is what DockerSandbox (T12)
                # actually reads to pick a matching node:<major> image, so
                # this adapter never has to know which Sandbox it's talking to.
                "TSBENCH_NODE_VERSION": version,
            }
        return self._pinned_env_cache[version]

    def _node_bin_dir(self, version: str) -> Path:
        """Resolve the bin dir for `version` via nvm, installing it (and
        enabling corepack for it, so pnpm/yarn shims exist under that
        specific node install) if it isn't already present."""
        script = (
            'export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; '
            f"nvm install {version} >&2 && nvm exec {version} corepack enable >&2 && nvm which {version}"
        )
        result = subprocess.run(["bash", "-lc", script], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"could not resolve node {version} via nvm:\n{result.stderr}")
        return Path(result.stdout.strip().splitlines()[-1]).parent

    def _detect_node_version(self, repo_path: Path, default: str = "20.11.1") -> str:
        for fname in (".nvmrc", ".node-version"):
            f = repo_path / fname
            if f.exists():
                v = f.read_text().strip().lstrip("v")
                if v:
                    return v
        return default

    def _detect_test_runner(self, repo_path: Path) -> str:
        pkg_json = repo_path / "package.json"
        deps = {}
        if pkg_json.exists():
            data = json.loads(pkg_json.read_text())
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

        found = [name for name, dep_key in _RUNNER_DEPS.items() if dep_key in deps]
        if len(found) == 1:
            return found[0]

        for name, configs in _RUNNER_CONFIGS.items():
            if any((repo_path / c).exists() for c in configs):
                return name

        if len(found) > 1:
            raise ValueError(f"Ambiguous test runner in {repo_path}: {found} all present")
        raise ValueError(f"No recognizable test runner in {repo_path}")

    def _detect_test_runner_with_fallback(self, package_path: Path, repo_path: Path) -> str:
        """
        Try the package's own directory first (a package can use a different
        runner than its siblings). If that fails and this is genuinely a
        monorepo (package_path != repo_path), fall back to the repo root --
        some monorepos share one runner config across all packages.
        Single-package repos (package_path == repo_path) get the original
        behavior unchanged: no fallback, the real error propagates.
        """
        try:
            return self._detect_test_runner(package_path)
        except ValueError:
            if package_path == repo_path:
                raise
            return self._detect_test_runner(repo_path)

    def _runner_bin(self, runner: str) -> str:
        """Path to the runner's own binary, already linked by install() into
        this package's node_modules/.bin -- resolved relative to
        run_tests()'s cwd (self.package_path), not invoked via `npx`.

        `npx <runner>` (npm's own `exec` command) is fragile here: a repo
        can declare an npm-style `"workspaces"` field in package.json while
        actually being pnpm-managed (e.g. zod). npm's `exec` then tries its
        own workspace resolution and fails with `Error: No workspaces
        found!` -- npm's own package-manager-mismatch confusion, nothing to
        do with the candidate patch or test outcome. The binary itself is
        already on disk after a successful install() regardless of which
        package manager put it there, so invoking it directly sidesteps the
        whole class of bug. Confirmed by direct repro against zod-6530's
        real base_commit: `npx vitest run` -> `No workspaces found!`,
        `./node_modules/.bin/vitest run` -> real JSON output, same install.
        """
        return f"./node_modules/.bin/{runner}"

    def _build_test_cmd(self, runner: str, test_ids: list[str] | None) -> list[str]:
        if runner == "vitest":
            cmd = [self._runner_bin(runner), "run", "--reporter=json", "--outputFile=vitest-results.json"]
            if test_ids:
                cmd += ["-t", "|".join(test_ids)]
            return cmd
        if runner == "jest":
            cmd = [self._runner_bin(runner), "--json", "--outputFile=jest-results.json"]
            if test_ids:
                cmd += test_ids
            return cmd
        if runner == "mocha":
            cmd = [self._runner_bin(runner), "--reporter", "json"]
            if test_ids:
                cmd += ["--grep", "|".join(test_ids)]
            return cmd
        raise ValueError(f"Unknown runner: {runner}")
