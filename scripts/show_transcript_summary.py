"""Print a compact turn-by-turn summary of a saved transcript.json: the
bash command extracted from each assistant turn (same extraction logic as
agent/loop.py's _extract_command), one line per turn. Lets you see a run's
behavioral pattern (stuck in a loop? never edits? explores then gives up?)
without reading the full JSON dump by eye.
"""

import json
import sys
from pathlib import Path

from agent.loop import CODE_BLOCK_RE

if len(sys.argv) < 2:
    print("Usage: uv run python scripts/show_transcript_summary.py <path-to-transcript.json>")
    sys.exit(1)

transcript = json.loads(Path(sys.argv[1]).read_text())

turn = 0
for msg in transcript:
    if msg["role"] != "assistant":
        continue
    turn += 1
    matches = CODE_BLOCK_RE.findall(msg["content"])
    command = matches[-1].strip() if matches else "(no code block found)"
    command_oneline = command.replace("\n", " \\n ")
    if len(command_oneline) > 120:
        command_oneline = command_oneline[:120] + "..."
    print(f"[{turn:2}] {command_oneline}")
