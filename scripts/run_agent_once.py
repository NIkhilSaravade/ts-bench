"""Manual one-off run of the reference agent against a single validated
instance. Prints the resulting patch, turn count, and whether the model
submitted explicitly or ran out of budget -- and saves the patch to
scratch/<instance_id>.patch so it can be re-scored later without having to
copy it out of terminal output. Also saves the full turn-by-turn transcript
to scratch/<instance_id>.transcript.json for debugging odd runs (e.g. a
model that submits immediately with no changes).

Deliberately does NOT score the patch itself -- that's what
scripts/score_saved_patch.py is for, separately.
"""

import json
import sys
from pathlib import Path

from agent.loop import run_agent
from pipeline.schema import TaskInstance

MIRRORS_DIR = Path("mirrors")
DATASET = Path("datasets/instances.jsonl")
SCRATCH_DIR = Path("scratch")

if len(sys.argv) < 2:
    print(
        "Usage: uv run python scripts/run_agent_once.py <model> [wall_clock_seconds] [instance_index_or_id]"
    )
    print('Example (OpenRouter):    uv run python scripts/run_agent_once.py "openrouter/some/model:free"')
    print(
        "Example (local):         uv run python scripts/run_agent_once.py "
        '"ollama_chat/qwen2.5-coder:14b" 1800'
    )
    print(
        "Example (2nd instance):  uv run python scripts/run_agent_once.py "
        '"ollama_chat/qwen2.5-coder:14b" 1800 1'
    )
    sys.exit(1)

model = sys.argv[1]
wall_clock_seconds = float(sys.argv[2]) if len(sys.argv) > 2 else None
instance_selector = sys.argv[3] if len(sys.argv) > 3 else None

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
print(f"Running agent on {instance.instance_id} with model={model}")

kwargs = {}
if wall_clock_seconds is not None:
    kwargs["wall_clock_seconds"] = wall_clock_seconds

result = run_agent(instance, MIRRORS_DIR, model=model, **kwargs)

print(f"\nSubmitted explicitly: {result.submitted}")
print(f"Turns used: {result.turns_used}")
print(f"Wall clock: {result.wall_clock_seconds:.1f}s")

SCRATCH_DIR.mkdir(exist_ok=True)

patch_path = SCRATCH_DIR / f"{instance.instance_id}.patch"
patch_path.write_text(result.patch)
print(f"\nPatch saved to {patch_path}")

transcript_path = SCRATCH_DIR / f"{instance.instance_id}.transcript.json"
transcript_path.write_text(json.dumps(result.transcript, indent=2))
print(f"Transcript saved to {transcript_path}")

print("\n--- patch ---")
print(result.patch if result.patch.strip() else "(empty patch)")
