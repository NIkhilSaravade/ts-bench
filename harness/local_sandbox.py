# harness/local_sandbox.py
import os
import subprocess
from pathlib import Path


class LocalSandbox:
    """v0.1 stand-in for the future Docker Sandbox — same shape, no isolation."""

    def run(self, cmd: list[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess:
        env = {**os.environ, "COREPACK_ENABLE_PROJECT_SPEC": "0"}
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
