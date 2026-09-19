"""Build the static leaderboard site: data/results.json + src/ -> site/.

Every number shown on the page is derived from data/results.json (written by
scripts/export_leaderboard_data.py from the raw run files). The only figures typed in here are the
fixed harness budget and the note about the separate LangGraph experiment, each with its source.

Usage: python3 leaderboard/build.py      (stdlib only; no npm needed)
Output: leaderboard/site/  (deploy this folder as-is to Cloudflare Pages)
"""
# The page copy lives in long f-strings; wrapping each sentence would make it harder to edit.
# ruff: noqa: E501

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
SITE = HERE / "site"
data = json.loads((HERE / "data" / "results.json").read_text())

# From docs/fairness_contract.md clause 3 (agent/loop.py MAX_TURNS, WALL_CLOCK_SECONDS).
TURNS, MINUTES = 40, 15
# From the separate ts-bench-langgraph project's docs/build-log.md, runs 3 and 4 (qwen3:14b, 5 Python
# tasks, one attempt each): patches written 1 of 5 before the setup fixes, 3 of 5 after; 0 solved.
LANGGRAPH_NOTE = (
    "although once we fixed problems in our own setup it wrote a patch on 3 of the 5 tasks, up from 1. "
    "None of those patches was correct."
)

esc = html.escape
models = data["models"]
insts = data["instances"]
attempts = data["attempts"]
totals = data["totals"]
ds = data["dataset"]


def pct(x: float) -> str:
    v = x * 100
    return f"{v:.1f}%" if v < 10 else f"{v:.0f}%"


def repo_short(repo: str) -> str:
    return repo.split("/")[-1]


def task_label(inst: dict) -> str:
    m = re.match(r"^.*-(\d+)$", inst["id"])
    return f"#{m.group(1)}" if m else inst["id"]


def month(d: str | None) -> str:
    if not d:
        return "unknown"
    y, mo = d.split("-")[:2]
    names = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{names[int(mo) - 1]} {y}"


# ---------- derived facts ----------
by_id = {m["id"]: m for m in models}
paid = [m for m in models if m["tier"] == "paid" and m["attempts"]]
local = [m for m in models if m["tier"] == "local" and m["attempts"]]
local_n = sum(m["attempts"] for m in local)
local_res = sum(m["resolved"] for m in local)
top = max(paid, key=lambda m: m["resolved"])  # the model with any fixes
top_idx = models.index(top)

fix_by_repo: dict[str, int] = {}
top_attempts_by_repo: dict[str, list[int]] = {}
for mi, ii, _rep, code in attempts:
    repo = insts[ii]["repo"]
    if code == 1:
        fix_by_repo[repo] = fix_by_repo.get(repo, 0) + 1
    if mi == top_idx:
        rec = top_attempts_by_repo.setdefault(repo, [0, 0])
        rec[1] += 1
        rec[0] += 1 if code == 1 else 0
lead_repo = max(fix_by_repo, key=fix_by_repo.get)
lead_fixes = fix_by_repo[lead_repo]
lead_top = top_attempts_by_repo.get(lead_repo, [0, 0])

dates = sorted(i["merge_date"] for i in insts if i["merge_date"])
old_n = len([d for d in dates if d < "2025-01-01"])
qwen3 = next(m for m in models if "qwen3" in m["id"])
gpt = next(m for m in models if "gpt-oss" in m["id"])
excluded_total = sum(m["infra_excluded"] for m in models)
lang_names = {"typescript": "TypeScript", "python": "Python", "java": "Java"}
language_line = ", ".join(
    f"{n} {lang_names.get(k, k)}" for k, n in sorted(ds["languages"].items(), key=lambda kv: -kv[1])
)

# ---------- limits (the up-front honesty block) ----------
limits = [
    (
        "Only one model fixed anything, and only 20 tries back it up.",
        f"{top['name']} fixed {top['resolved']} of {top['attempts']} bugs. With so few tries the honest range is "
        f"{pct(top['ci_low'])} to {pct(top['ci_high'])}. It covers {top['instances_covered']} of {top['instances_total']} "
        f"tasks because the paid budget ran out, and it got one attempt per task, so luck could move that number a lot.",
    ),
    (
        f"{lead_fixes} of the {totals['resolved']} fixes came from one project.",
        f"Those {lead_fixes} are all in {repo_short(lead_repo)}. {top['name']} fixed {lead_top[0]} of the {lead_top[1]} {repo_short(lead_repo)} "
        f"tasks it tried. That says the tasks in one repository were easier for it, not that it is good at every codebase.",
    ),
    (
        "The free models scored zero, under one deliberately plain setup.",
        f"Across {local_n} attempts, {', '.join(m['name'] for m in local[:-1])} and {local[-1]['name']} fixed {local_res}. "
        f"Their agent types one shell command per turn, with {TURNS} turns and {MINUTES} minutes. "
        f"That does not prove these models can't fix these bugs with better tooling.",
    ),
    (
        "Two planned models are incomplete or missing.",
        f"{gpt['name']} was never run, so it has no score and is not shown as zero. {qwen3['name']} stopped at "
        f"{qwen3['attempts']} of {qwen3['planned_attempts']} attempts, covering {qwen3['instances_covered']} of "
        f"{qwen3['instances_total']} tasks.",
    ),
    (
        "Older tasks may already be in a model's training data.",
        f"{old_n} of the {len(insts)} real fixes were merged before 2025, the oldest in {month(dates[0])}. We haven't "
        f"recorded each model's training cutoff yet, so nothing on this page is labelled for contamination. That is "
        f"a gap, not a clean bill.",
    ),
    (
        f"It is a small set: {len(insts)} tasks.",
        f"{ds['repos']} repositories: {language_line}. Java tasks are the hardest to build, and the set was "
        f"grown by hand-checking candidates, not sampled at random.",
    ),
]
limits_html = "\n      ".join(f'<div class="limit"><h3>{esc(h)}</h3><p>{esc(p)}</p></div>' for h, p in limits)

# ---------- leaderboard rows ----------
AXIS_MAX = 0.60


def row(m: dict) -> str:
    if m["status"] == "not_run":
        cls = "is-off"
    elif m["resolved"]:
        cls = "is-fix"
    else:
        cls = "is-none"
    tier = "paid API" if m["tier"] == "paid" else "local, free"
    if m["attempts"]:
        fixed = f"<b>{m['resolved']}</b> of {m['attempts']}"
        left = m["ci_low"] / AXIS_MAX * 100
        width = max((m["ci_high"] - m["ci_low"]) / AXIS_MAX * 100, 0.6)
        dot = m["rate"] / AXIS_MAX * 100
        rng = (
            f'<div class="range"><div class="range__track"><div class="range__ink">'
            f'<div class="range__band" style="left:{left:.2f}%;width:{width:.2f}%"></div>'
            f'<div class="range__dot" style="left:{dot:.2f}%"></div></div></div>'
            f"<small>{pct(m['ci_low'])} to {pct(m['ci_high'])}</small></div>"
        )
        cost = f"${m['cost_usd']:.2f}" if m["cost_usd"] else "Free"
        pill_cls = "pill pill--partial" if m["status"] == "partial" else "pill"
        pill_txt = "Stopped early" if m["status"] == "partial" else "Complete"
    else:
        fixed = "No data"
        rng = "<small>Never run</small>"
        cost = "None"
        pill_cls, pill_txt = "pill pill--off", "Not run"
    cov = f"{m['instances_covered']} of {m['instances_total']}" if m["attempts"] else "None"
    return (
        f'<tr class="{cls}"><th scope="row">{esc(m["name"])}<small>{esc(m["maker"])}, {tier}</small></th>'
        f'<td class="num">{fixed}</td><td>{rng}</td><td class="num">{cost}</td>'
        f'<td class="num">{cov}</td><td><span class="{pill_cls}">{pill_txt}</span></td></tr>'
    )


order = sorted(models, key=lambda m: (m["status"] == "not_run", -(m["resolved"]), -m["attempts"]))
rows_html = "\n        ".join(row(m) for m in order)
cost_note = (
    f"Paid spend was ${by_id[top['id']]['cost_usd']:.2f} of a $10 budget, about ${top['cost_per_attempt']:.2f} per attempt. "
    f"A further {data['smoke_test']['attempts']} attempts by {data['smoke_test']['model']} (${data['smoke_test']['cost_usd']:.2f}) "
    f"were early smoke tests, fixed {data['smoke_test']['resolved']}, and are too few to rank."
)

# ---------- task matrix ----------
shown = [mi for mi, m in enumerate(models) if m["attempts"]]
shown.sort(key=lambda mi: (-models[mi]["resolved"], -models[mi]["attempts"]))
counts: dict[tuple[int, int], list[int]] = {}
for mi, ii, _rep, code in attempts:
    rec = counts.setdefault((mi, ii), [0, 0])
    rec[1] += 1
    rec[0] += 1 if code == 1 else 0
matrix_head = "".join(
    f'<th scope="col" class="m" data-col="{c}">{esc(models[mi]["name"])}</th>' for c, mi in enumerate(shown)
)
mrows: list[str] = []
current = None
for ii, inst in enumerate(insts):
    if inst["repo"] != current:
        current = inst["repo"]
        n = len([i for i in insts if i["repo"] == current])
        lang = lang_names.get(inst["language"], inst["language"])
        mrows.append(
            f'<tr class="grp"><th scope="colgroup" colspan="{2 + len(shown)}">{esc(current)}'
            f"<span>{lang}, {n} tasks</span></th></tr>"
        )
    cells = []
    for c, mi in enumerate(shown):
        rec = counts.get((mi, ii))
        if not rec:
            cells.append(f'<td class="m none" data-col="{c}"><span>not run</span></td>')
        else:
            cls = "m hit" if rec[0] else "m"
            cells.append(f'<td class="{cls}" data-col="{c}"><span>{rec[0]}/{rec[1]}</span></td>')
    mrows.append(
        f'<tr><th scope="row">{task_label(inst)}</th><td class="when">{month(inst["merge_date"])}</td>{"".join(cells)}</tr>'
    )
matrix_html = "\n        ".join(mrows)

stage_alt = (
    f"{totals['attempts']} squares, one per attempt. {totals['resolved']} are highlighted as fixed; "
    f"the rest did not fix the bug. The same figures are in the table below."
)
meta_description = (
    f"{totals['resolved']} fixes in {totals['attempts']} attempts: an honest benchmark of AI coding agents on "
    f"{ds['instances']} real bugs from open-source projects, with the limits stated up front."
)
favicon = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 22 22'%3E"
    "%3Crect width='22' height='22' rx='4' fill='%23E8EBF3'/%3E"
    "%3Ccircle cx='11' cy='11' r='6' fill='%23F0287D' stroke='%23151A3D' stroke-width='2'/%3E%3C/svg%3E"
)

excluded_note = (
    f"{excluded_total} attempts were excluded across all models."
    if excluded_total
    else "None of the attempts on this page were excluded."
)

values = {
    "meta_description": esc(meta_description, quote=True),
    "favicon": favicon,
    "resolved": str(totals["resolved"]),
    "attempts": str(totals["attempts"]),
    "instances": str(ds["instances"]),
    "repos": str(ds["repos"]),
    "stage_alt": esc(stage_alt, quote=True),
    "limits": limits_html,
    "rows": rows_html,
    "cost_note": esc(cost_note),
    "matrix_head": matrix_head,
    "matrix": matrix_html,
    "turns": str(TURNS),
    "minutes": str(MINUTES),
    "excluded_note": esc(excluded_note),
    "lg_note": esc(LANGGRAPH_NOTE),
    "dataset_version": esc(ds["version"]),
    "language_line": esc(language_line),
    "generated_at": esc(data["generated_at"]),
    "cost": f"{totals['cost_usd']:.2f}",
    "data_json": json.dumps(data, separators=(",", ":")).replace("</", "<\\/"),
}

template = (SRC / "template.html").read_text()
missing = set(re.findall(r"\{\{(\w+)\}\}", template)) - set(values)
if missing:
    raise SystemExit(f"template placeholders with no value: {sorted(missing)}")
page = re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], template)

if SITE.exists():
    shutil.rmtree(SITE)
(SITE / "assets").mkdir(parents=True)
(SITE / "index.html").write_text(page)
shutil.copy(SRC / "style.css", SITE / "assets" / "style.css")
shutil.copy(SRC / "app.js", SITE / "assets" / "app.js")
(SITE / "_headers").write_text(
    "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n"
    "  X-Frame-Options: DENY\n/assets/*\n  Cache-Control: public, max-age=3600\n"
)
print(
    f"built {SITE.relative_to(HERE.parent)}: index.html {len(page) / 1024:.0f} KB, "
    f"{totals['attempts']} attempts, {totals['resolved']} fixed"
)
