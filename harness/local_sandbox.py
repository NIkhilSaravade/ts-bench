import os
import signal
import subprocess
from pathlib import Path


class LocalSandbox:
    """v0.1 stand-in for the future Docker Sandbox — same shape, no isolation."""

    def run(
        self,
        cmd: list[str],
        cwd: Path,
        timeout: int = 300,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess:
        env = {**os.environ, "CI": "1", **(extra_env or {})}
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,  # child becomes its own process-group leader
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.communicate()  # reap so it doesn't zombie
            raise TimeoutError(f"{' '.join(cmd)} exceeded {timeout}s in {cwd}") from None
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
