# harness/tests/stability_check_trpc.py
from pathlib import Path

from harness.local_sandbox import LocalSandbox
from harness.ts_adapter import TypeScriptAdapter

repo = Path.home() / "scratch" / "repos" / "trpc"
package = repo / "packages" / "server"
adapter = TypeScriptAdapter(repo_path=repo, package_path=package)
sandbox = LocalSandbox()
env = adapter.detect_environment(repo)

maps = []
for i in range(2):
    raw = adapter.run_tests(sandbox, env, test_ids=None)
    result = adapter.parse_results(raw, env.test_runner)
    maps.append(result)
    print(f"Run {i + 1}: {sum(result.values())}/{len(result)} passed")

print("STABLE" if maps[0] == maps[1] else "UNSTABLE")
