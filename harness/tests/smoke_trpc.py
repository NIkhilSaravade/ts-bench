# harness/tests/smoke_trpc.py
from pathlib import Path

from harness.local_sandbox import LocalSandbox
from harness.ts_adapter import TypeScriptAdapter

repo = Path.home() / "scratch" / "repos" / "trpc"
package = repo / "packages" / "server"

adapter = TypeScriptAdapter(repo_path=repo, package_path=package)
sandbox = LocalSandbox()

env = adapter.detect_environment(repo)
print("Detected environment:", env)

adapter.install(sandbox, env)
print("Install done")

raw = adapter.run_tests(sandbox, env, test_ids=None)
results = adapter.parse_results(raw, env.test_runner)
print(f"{sum(results.values())}/{len(results)} tests passed")
