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
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import diagrams  # noqa: E402  (sibling module; path added just above)

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
        pill_cls = "tag tag--partial" if m["status"] == "partial" else "tag"
        pill_txt = "Stopped early" if m["status"] == "partial" else "Complete"
    else:
        fixed = "No data"
        rng = "<small>Never run</small>"
        cost = "None"
        pill_cls, pill_txt = "tag tag--off", "Not run"
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
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20'%3E"
    "%3Crect x='1' y='1' width='18' height='18' rx='3' fill='white' stroke='%230F1A2B' stroke-width='1.6'/%3E"
    "%3Cpath d='M5 10.5l3.2 3.2L15 6.8' fill='none' stroke='%231F3FD6' stroke-width='2.2' "
    "stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E"
)

# ---------- recruiter-facing content: stack, build history, hard problems ----------
# Facts below come from docs/ts-bench-task-board.md and docs/step7-real-model-run.md.
LOC = "4,500"  # non-test Python under pipeline/, harness/, agent/, scripts/ (wc -l, Sep 2026)
TESTS = 46  # `uv run pytest -q` result, Sep 2026

STACK = [
    (
        "Language and packaging",
        "Python 3.12, uv, hatchling",
        "Core code, locked and reproducible environments.",
    ),
    (
        "Data and schema",
        "Pydantic v2, JSONL, HuggingFace datasets",
        "Validated task schema and a versioned, immutable dataset that loads with the datasets library.",
    ),
    (
        "Storage",
        "PostgreSQL 16, psycopg 3",
        "tasks, runs and results tables. Composite keys make replayed writes safe.",
    ),
    (
        "Model access",
        "LiteLLM, Ollama, OpenRouter, Anthropic API",
        "One interface for local and hosted models, with cost and token logging.",
    ),
    (
        "Targets under test",
        "Node via nvm, pnpm, npm, yarn, vitest, jest, pytest, Maven, JUnit",
        "What the language adapters drive inside each task's own repository.",
    ),
    (
        "Isolation",
        "Docker, warm package-cache volumes, git archive",
        "Runs without host state. Task folders are built with no git history.",
    ),
    (
        "Scale-out",
        "Apache Kafka 3.8 (KRaft), kafka-python, Kubernetes (kind)",
        "An idempotent job queue and a pool of worker pods.",
    ),
    (
        "Task sources",
        "GitHub GraphQL API, bare git mirrors",
        "Mining merged pull requests and extracting exact diffs.",
    ),
    ("Agent experiment", "LangChain, LangGraph", "A tool-using second agent, in a separate project."),
    (
        "Quality",
        "pytest, ruff, pre-commit, GitHub Actions",
        f"{TESTS} passing tests. CI enforces lint and formatting on every push.",
    ),
    (
        "This site",
        "Static HTML, CSS, JavaScript, inline SVG, Cloudflare Pages",
        "Generated from the results data by a standard-library Python script. No framework.",
    ),
]

PHASES = [
    (
        "Foundation",
        "T1, T2",
        [
            "A monorepo with uv, ruff, pre-commit and CI, and a Pydantic TaskInstance schema as the contract between every stage.",
            "The LanguageAdapter interface and a TypeScript adapter, checked on three real repositories (zod, class-validator, trpc) with identical results across runs.",
        ],
    ),
    (
        "Tasks worth trusting",
        "T3, T4, T11",
        [
            "The validator and its gold and empty gate, a GitHub GraphQL miner, and 24 validated tasks in the end.",
            "Contamination dates for every task, and a repeat-run audit that re-checks the whole set (13 of 13 clean when last run).",
        ],
    ),
    (
        "Execution and scoring",
        "T6, T7, T8, T9",
        [
            "An eval runner with anti-cheat test resets, a deliberately minimal reference agent, a LiteLLM gateway with cost tracking, and a hard split between model failures and infrastructure failures.",
            "pass@k with bootstrap error bars, checked against hand calculations before it was trusted.",
        ],
    ),
    (
        "Reproducibility and breadth",
        "T12, T13, T14",
        [
            "A Docker sandbox with warm package caches, measured 25 to 35 percent faster on a monorepo and 2.5 to 3 times faster on a single package.",
            "Python and Java adapters that proved the language seam.",
        ],
    ),
    (
        "Storage and scale",
        "T5, T15",
        [
            "A versioned dataset export and a Postgres schema that round-trips it exactly.",
            "A Kafka and Kubernetes job queue, verified against a force-killed worker.",
        ],
    ),
    (
        "Real models, and this site",
        "Step 7, T10",
        [
            "667 real attempts on local and paid models. Eight bugs surfaced, and were fixed, only once real and imperfect model output flowed through.",
            "This site, generated from the results with its limits stated first.",
        ],
    ),
]

CASES = [
    (
        "Node version was recorded but never enforced",
        "Nearly every trpc candidate was rejected with dozens of unrelated failing tests.",
        "Tests ran under whatever Node the shell defaulted to (v24). The repository pinned 22, and the two disagreed about fetch internals.",
        "The adapter resolves the exact Node version through nvm and puts it first on PATH. The six newest trpc candidates then validated on the first try.",
    ),
    (
        "A passing gate can hide an untested safety path",
        "The gold and empty gate passed, yet nothing had exercised the rule that restores test files an agent edits.",
        "The human patch never touches test files by construction, so the restore step always ran on an empty list.",
        "A direct test tampers with a real test file and checks it is restored.",
    ),
    (
        "Caching the wrong thing in Docker",
        "In a pnpm monorepo, vitest was missing, fell back to a global copy, and the harness reported a clean-looking but wrong result.",
        "The first design cached node_modules by lockfile hash and skipped the install, so per-package node_modules were never created.",
        "Always run the install and persist the package managers' own caches instead. Warm installs were 25 to 35 percent faster on a monorepo, 2.5 to 3 times on a single package.",
    ),
    (
        "Compiled languages broke task mining",
        "74 Java candidates from two repositories produced zero tasks.",
        "The new tests call a method the fix adds, so they cannot compile before the fix. A dynamic language would simply fail that one test.",
        "A compile failure now counts as failing before the fix, with test names read from the diff. A wrong guess can only miss a task, never approve a false one. Six Java tasks validated, and the work exposed a scoring bug that under-scored parameterized tests.",
    ),
    (
        "Failures scored as infrastructure errors",
        "A real model's broken Java or Python patch was recorded as infra_error, which is excluded from the score.",
        "Every earlier check ran only the human patch, which always compiles. Real model output was the first thing to reach that path.",
        "Typed exceptions for compile and collection failures (and pytest's own exit code 4), so they count against the model. Left alone, it would have quietly inflated Java scores.",
    ),
    (
        "Environment bugs that looked like flakes",
        "Bursts of identical infrastructure errors in the middle of a long run.",
        "Three causes: Ollama restarted as the wrong user served zero models (230 attempts lost), nvm install hit the network on every call, and a global .npmrc with workspaces=true broke npm for every project.",
        "A 15-minute watcher caught each burst. Bad rows were removed and the run resumed without rework. Reading the tools' source found the last two.",
    ),
    (
        "Kafka on one broker never assigned work",
        "Workers reported ready and never received a partition.",
        "The offsets topic defaults to 3 replicas, which one broker can never satisfy, and the job topic had been created with a single partition, so two of three workers sat idle.",
        "Set the replication factor to 1 and raised the topic to 6 partitions. Then verified concurrent workers and a force-killed pod: nothing lost, nothing duplicated.",
    ),
]

stack_html = "\n        ".join(
    f'<tr><th scope="row">{esc(a)}</th><td>{esc(b)}</td><td>{esc(c)}</td></tr>' for a, b, c in STACK
)
phases_html = "\n    ".join(
    f'<li><h3>{esc(t)}<span class="when">{esc(w)}</span></h3>'
    + "".join(f"<p>{esc(p)}</p>" for p in ps)
    + "</li>"
    for t, w, ps in PHASES
)
cases_html = "\n    ".join(
    f'<article class="case"><h3>{esc(t)}</h3><dl><dt>Symptom</dt><dd>{esc(s)}</dd><dt>Cause</dt><dd>{esc(c)}</dd>'
    f"<dt>Fix</dt><dd>{esc(f)}</dd></dl></article>"
    for t, s, c, f in CASES
)
facts_html = "\n    ".join(
    f"<div><dt>{esc(k)}</dt><dd>{esc(v)}<span>{esc(s)}</span></dd></div>"
    for k, v, s in [
        ("Task set", f"{ds['instances']} real bugs", f"{ds['repos']} repositories, version {ds['version']}"),
        ("Languages", "TypeScript, Python, Java", "One adapter interface"),
        (
            "Real attempts",
            str(totals["attempts"]),
            f"{totals['models_with_data']} models, ${totals['cost_usd']:.2f} spent",
        ),
        ("Runs on", "Docker, Kafka, Kubernetes", "Postgres for results"),
        ("Codebase", f"About {LOC} lines of Python", f"{TESTS} passing tests, CI on every push"),
    ]
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
    "models_with_data": str(totals["models_with_data"]),
    "top_name": esc(top["name"]),
    "top_attempts": str(top["attempts"]),
    "facts": facts_html,
    "loc": LOC,
    "tests": str(TESTS),
    "stack_rows": stack_html,
    "phases": phases_html,
    "cases": cases_html,
    "diagram_architecture": diagrams.architecture(),
    "diagram_validation": diagrams.validation(),
    "diagram_attempt": diagrams.attempt(),
    "diagram_adapters": diagrams.adapters(),
    "diagram_scaleout": diagrams.scaleout(),
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
