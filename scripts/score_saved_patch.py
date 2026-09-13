"""Score a saved agent patch against harness/eval_runner.py's evaluate(),
without re-running the agent. Use this to see exactly how the harness
scores a patch you already have on disk -- clean unresolved, a
patch-apply failure, or an infra error -- without spending more model
calls to reproduce it.
"""

import sys
from pathlib import Path

from harness.eval_runner import evaluate
from pipeline.schema import TaskInstance

MIRRORS_DIR = Path("mirrors")
DATASET = Path("datasets/instances.jsonl")

if len(sys.argv) < 2:
    print("Usage: uv run python scripts/score_saved_patch.py <patch_file> [instance_index_or_id]")
    sys.exit(1)

patch_path = Path(sys.argv[1])
patch = patch_path.read_text()
instance_selector = sys.argv[2] if len(sys.argv) > 2 else None

lines = DATASET.read_text().splitlines()

if instance_selector is None:
    chosen_line = lines[0]
elif instance_selector.isdigit():
    chosen_line = lines[int(instance_selector)]
else:
    matches = [line for line in lines if f'"instance_id": "{instance_selector}"' in line]
    if not matches:
        print(f"No instance found with instance_id={instance_selector!r}")
        sys.exit(1)
    chosen_line = matches[0]

instance = TaskInstance.model_validate_json(chosen_line)
print(f"Scoring {patch_path} against {instance.instance_id}")

result = evaluate(instance, patch, MIRRORS_DIR)

print(f"\nStatus: {result.status}")
print(f"Resolved: {result.resolved}")
print(f"Wall clock: {result.wall_clock_seconds:.1f}s")
print(f"Patch strategy: {result.patch_strategy}")
print(f"FAIL_TO_PASS results: {result.fail_to_pass_results}")
print(f"PASS_TO_PASS results: {result.pass_to_pass_results}")
if result.stderr_tail:
    print(f"\nStderr tail:\n{result.stderr_tail}")
