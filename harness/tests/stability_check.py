from pathlib import Path

from harness.local_sandbox import LocalSandbox
from harness.ts_adapter import TypeScriptAdapter

repo = Path.home() / "scratch" / "repos" / "zod"
adapter = TypeScriptAdapter(repo_path=repo)
sandbox = LocalSandbox()
env = adapter.detect_environment(repo)

maps = []
for i in range(2):
    raw = adapter.run_tests(sandbox, env, test_ids=None)
    result = adapter.parse_results(raw, env.test_runner)
    maps.append(result)
    print(f"Run {i + 1}: {sum(result.values())}/{len(result)} passed")

if maps[0] == maps[1]:
    print("STABLE: identical results across runs")
else:
    diff = set(maps[0]) ^ set(maps[1]) | {k for k in maps[0] if maps[0].get(k) != maps[1].get(k)}
    print(f"UNSTABLE: {len(diff)} tests diverged")
    for k in list(diff)[:10]:
        print(f"  {k}: run1={maps[0].get(k)} run2={maps[1].get(k)}")
