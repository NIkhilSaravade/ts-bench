"""One-off smoke test for agent/workspace.py.

Not part of the eval loop -- just proof the materialize -> git-init ->
edit -> diff -> cleanup mechanics actually work, before T7's agent loop
(sub-task 3) is built on top of them.
"""

from pathlib import Path

from agent.workspace import agent_workspace, extract_patch
from pipeline.schema import TaskInstance

MIRRORS_DIR = Path("mirrors")
DATASET = Path("datasets/instances.jsonl")

first_line = DATASET.read_text().splitlines()[0]
instance = TaskInstance.model_validate_json(first_line)
print(f"Using instance: {instance.instance_id}")

with agent_workspace(instance, MIRRORS_DIR) as ws:
    print(f"Workspace materialized at: {ws}")
    assert (ws / ".git").exists(), "expected a git repo"

    readme = ws / "README.md"
    assert readme.exists(), "adjust this to touch a file that exists in your repo"
    readme.write_text(readme.read_text() + "\n<!-- smoke test edit -->\n")

    patch = extract_patch(ws)
    print("--- patch ---")
    print(patch)
    assert "smoke test edit" in patch, "edit didn't show up in the diff"
    print("OK: edit appeared correctly in the extracted patch")

    ws_after = ws

assert not ws_after.exists(), "expected workspace to be cleaned up on exit"
print("OK: workspace was cleaned up after the context manager exited")
