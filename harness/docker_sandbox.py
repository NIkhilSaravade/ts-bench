"""T12: a Docker-backed Sandbox, implementing the exact same `run()` shape
`LocalSandbox` does -- a drop-in swap, nothing above the Sandbox interface
changes.

Real isolation is the headline feature (a stranger's machine, not this
host's globally-installed corepack/pnpm/npm cache), but the concrete cost
this task exists to attack is the one T9 measured directly: `evaluate()`
reinstalls dependencies from scratch on every single call.

An earlier version of this file tried to cache node_modules itself (a
named Docker volume, skipping the install command outright once "ready").
That broke on a real monorepo (trpc): pnpm creates node_modules in
MULTIPLE places (the workspace root AND every individual package), and
skipping the install command meant the fresh, never-before-seen working
tree for a NEW evaluate() call never got its per-package node_modules
populated at all -- `packages/server/node_modules` simply didn't exist,
and `npx vitest` silently fell back to downloading an unrelated global
copy instead of erroring loudly. The actual, correct fix is much simpler
and is what real-world pnpm/npm/yarn caching already does: never skip the
install command -- just keep each package manager's own global,
content-addressable CACHE (not node_modules) warm in a persisted volume.
A warm-cache install still runs in full (correctly repopulating
node_modules for whatever fresh tree exists right now) but does no network
work, which is where the real cost was all along.
"""

import subprocess
import uuid
from pathlib import Path

# One shared cache per package manager, reused across every repo and every
# instance -- this is exactly what these caches are FOR (content-addressable
# by package name+version, not by project), so cross-repo sharing is a
# correctness-preserving bonus, not a risk.
_PNPM_STORE_VOLUME = "tsbench-pnpm-store"
_NPM_CACHE_VOLUME = "tsbench-npm-cache"
_YARN_CACHE_VOLUME = "tsbench-yarn-cache"
# Corepack itself downloads the actual pnpm/yarn CLI binary (not a project
# dependency, the tool itself) fresh in every ephemeral container unless
# this is persisted too -- caught as an intermittent "install failed" when a
# corepack download hit a transient network blip (this environment's known
# WSL2 IPv6-routing flakiness, see T2's notes), not a real, reproducible bug.
_COREPACK_CACHE_VOLUME = "tsbench-corepack-cache"


class DockerSandbox:
    def __init__(self, default_image: str = "node:22-bookworm"):
        self.default_image = default_image

    def _image_for(self, extra_env: dict[str, str] | None) -> str:
        version = (extra_env or {}).get("TSBENCH_NODE_VERSION")
        if not version:
            return self.default_image
        major = version.split(".")[0]
        return f"node:{major}-bookworm"

    def run(
        self,
        cmd: list[str],
        cwd: Path,
        timeout: int = 300,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess:
        image = self._image_for(extra_env)

        # node:X images ship corepack but don't enable its pnpm/yarn shims by
        # default -- same as a fresh nvm install on the host (T3's finding).
        # Enabling it is instant and local (no network), so it's cheapest to
        # just always do it rather than detect which package manager cmd needs it.
        shell_cmd = "corepack enable && " + " ".join(cmd)

        container_name = f"tsbench-run-{uuid.uuid4().hex[:12]}"
        # Bind-mount cwd at the SAME absolute path inside the container (not
        # some fixed "/workspace") -- TypeScriptAdapter.parse_results()
        # computes test-ID paths relative to self.repo_path, a host path. A
        # container that reports a different internal path for the same
        # files would silently break that relative_to() call; matching paths
        # exactly means the adapter needs zero knowledge of which sandbox
        # backend produced the raw output. node_modules itself is NOT a
        # separate volume -- it lives on this same bind mount, exactly like
        # LocalSandbox, so a monorepo's per-package node_modules dirs get
        # created normally by whatever install command actually runs.
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "-v",
            f"{cwd}:{cwd}",
            "-v",
            f"{_PNPM_STORE_VOLUME}:/caches/pnpm-store",
            "-v",
            f"{_NPM_CACHE_VOLUME}:/caches/npm-cache",
            "-v",
            f"{_YARN_CACHE_VOLUME}:/caches/yarn-cache",
            "-v",
            f"{_COREPACK_CACHE_VOLUME}:/caches/corepack-cache",
            "-e",
            "npm_config_store_dir=/caches/pnpm-store",
            "-e",
            "npm_config_cache=/caches/npm-cache",
            "-e",
            "YARN_CACHE_FOLDER=/caches/yarn-cache",
            "-e",
            "COREPACK_HOME=/caches/corepack-cache",
            "-w",
            str(cwd),
            # Without this, Corepack's "about to download pnpm X, continue?"
            # prompt hangs forever with no TTY to answer it (the same
            # LocalSandbox finding from T4 -- Corepack only skips the prompt
            # "when standard input is a TTY and no CI environment is detected").
            "-e",
            "CI=1",
        ]
        for k, v in (extra_env or {}).items():
            if k == "PATH":
                continue  # a host nvm PATH is meaningless inside the container
            docker_cmd += ["-e", f"{k}={v}"]
        docker_cmd += [image, "bash", "-lc", shell_cmd]

        try:
            result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", container_name], capture_output=True)
            raise TimeoutError(f"{shell_cmd} exceeded {timeout}s in container {container_name}") from None

        return subprocess.CompletedProcess(cmd, result.returncode, result.stdout, result.stderr)
