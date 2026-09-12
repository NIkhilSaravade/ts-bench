# harness/tests/smoke_zod.py
from pathlib import Path

from harness.local_sandbox import LocalSandbox
from harness.ts_adapter import TypeScriptAdapter

repo = Path.home() / "scratch" / "repos" / "zod"
adapter = TypeScriptAdapter(repo_path=repo)
sandbox = LocalSandbox()

env = adapter.detect_environment(repo)
print("Detected environment:", env)

adapter.install(sandbox, env)
print("Install done")

raw = adapter.run_tests(sandbox, env, test_ids=None)
results = adapter.parse_results(raw, env.test_runner)
print(f"{sum(results.values())}/{len(results)} tests passed")
