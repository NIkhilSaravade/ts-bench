"""Architecture diagrams for the leaderboard site, drawn as inline SVG.

Each function returns one <svg> string. Styling is done in src/style.css through the dg-* classes so
the diagrams follow the page theme. Every box, arrow and label below reflects something that exists
in the repository (see docs/ts-bench-task-board.md); nothing is decorative.
"""
# Diagram copy is written as long single-line strings so each box reads as one unit.
# ruff: noqa: E501

from __future__ import annotations

import html
from textwrap import wrap

esc = html.escape

# Rough average glyph widths (px) at the diagram font sizes, used to wrap text inside boxes.
CHAR_PX = 7.1
NOTE_CHAR_PX = 7.6


class Diagram:
    def __init__(self, width: int, height: int, label: str):
        self.w, self.h, self.label = width, height, label
        self.parts: list[str] = []

    def band(self, x, y, w, h, title, sub=""):
        self.parts.append(f'<rect class="dg-band" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>')
        self.parts.append(f'<text class="dg-band-title" x="{x + 18}" y="{y + 32}">{esc(title)}</text>')
        for i, line in enumerate(wrap(sub, 21)):
            self.parts.append(
                f'<text class="dg-band-sub" x="{x + 18}" y="{y + 54 + i * 17}">{esc(line)}</text>'
            )

    def node(self, x, y, w, h, title, sub="", kind="core", lines=None):
        out = [
            f'<g class="dg-node k-{kind}"><title>{esc(title)}: {esc(sub or " ".join(lines or []))}</title>'
        ]
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4"/>')
        out.append(f'<text class="dg-title" x="{x + 14}" y="{y + 25}">{esc(title)}</text>')
        rows = lines if lines is not None else wrap(sub, max(8, int((w - 28) / CHAR_PX)))
        for i, line in enumerate(rows):
            out.append(f'<text class="dg-sub" x="{x + 14}" y="{y + 47 + i * 17}">{esc(line)}</text>')
        out.append("</g>")
        self.parts.append("".join(out))

    def arrow(self, d, flow=True, dashed=False, label="", lx=0, ly=0, anchor="middle"):
        cls = "dg-edge" + (" flow" if flow and not dashed else "") + (" dashed" if dashed else "")
        self.parts.append(f'<path class="{cls}" d="{d}" marker-end="url(#ah)"/>')
        if label:
            self.parts.append(
                f'<text class="dg-label" x="{lx}" y="{ly}" text-anchor="{anchor}">{esc(label)}</text>'
            )

    def note(self, x, y, w, h, text):
        rows = wrap(text, max(10, int((w - 28) / NOTE_CHAR_PX)))
        self.parts.append(f'<g class="dg-note"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4"/>')
        for i, line in enumerate(rows):
            self.parts.append(f'<text x="{x + 14}" y="{y + 26 + i * 19}">{esc(line)}</text>')
        self.parts.append("</g>")

    def text(self, x, y, s, cls="dg-label", anchor="start"):
        self.parts.append(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{esc(s)}</text>')

    def dashed_box(self, x, y, w, h, title):
        self.parts.append(f'<rect class="dg-group" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>')
        self.parts.append(f'<text class="dg-group-title" x="{x + 14}" y="{y + 23}">{esc(title)}</text>')

    def svg(self) -> str:
        defs = (
            '<defs><marker id="ah" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" '
            'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="dg-head"/></marker></defs>'
        )
        return (
            f'<svg class="dg" viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{esc(self.label, quote=True)}" '
            f'xmlns="http://www.w3.org/2000/svg">{defs}{"".join(self.parts)}</svg>'
        )


# ---------------------------------------------------------------------------------------------
def architecture() -> str:
    # Layer heights; y positions are computed so boxes always sit inside their band.
    specs = [
        ("Presentation", "What people see", 110),
        ("Orchestration", "Runs many jobs at once", 138),
        ("Execution harness", "Runs one attempt and scores it", 196),
        ("Task pipeline", "Turns real fixes into checked tasks", 146),
        ("Data and sources", "Where everything lives", 112),
    ]
    gap = 24
    ys, y = [], 12
    for _, _, h in specs:
        ys.append(y)
        y += h + gap
    d = Diagram(
        1200,
        y - gap + 12,
        "Layered system architecture: presentation, orchestration, harness, pipeline, data.",
    )
    for (title, sub, h), ly in zip(specs, ys, strict=True):
        d.band(8, ly, 1184, h, title, sub)
    top = [ly + 18 for ly in ys]
    hs = [h - 36 for _, _, h in specs]
    X0 = 214

    # presentation
    d.node(
        X0,
        top[0],
        480,
        hs[0],
        "Leaderboard site",
        "Static HTML, CSS and JavaScript, generated from the results data.",
        "out",
    )
    d.node(
        714,
        top[0],
        470,
        hs[0],
        "Statistics",
        "Fix rate with Wilson 95% ranges, pass@k with bootstrap error bars, cost per attempt.",
        "out",
    )

    # orchestration
    d.node(X0, top[1], 200, hs[1], "Job producer", "One job per model, task and repeat.")
    d.node(444, top[1], 200, hs[1], "Kafka topic", "KRaft mode, 6 partitions.")
    d.node(
        674,
        top[1],
        270,
        hs[1],
        "Worker pods",
        "Kubernetes consumer group of 3. Each result is written once, even if a job is replayed.",
    )
    d.node(
        974,
        top[1],
        210,
        hs[1],
        "Sequential driver",
        "run_driver.py. Same harness, one process, resumable results file.",
    )
    mid = top[1] + hs[1] // 2
    d.arrow(f"M414 {mid}H442")
    d.arrow(f"M644 {mid}H672")
    d.arrow(
        f"M760 {top[1] + hs[1]}V{top[2]}",
        label="run job",
        lx=772,
        ly=(top[1] + hs[1] + top[2]) // 2 + 4,
        anchor="start",
    )

    # harness
    xs = [214, 406, 598, 790, 982]
    ws = [176, 176, 176, 176, 202]
    hn = [
        ("Model gateway", "LiteLLM. One interface for Ollama, OpenRouter, Anthropic and a mock model."),
        ("Agent scaffold", "One command per turn. 40 turns and 15 minutes, identical for every model."),
        ("Eval runner", "Resets test files, applies the patch, adds hidden tests, runs, scores."),
        ("LanguageAdapter", "Four methods. TypeScript, Python and Java plug in here."),
        ("Sandbox", "A local process, or Docker with warm package caches."),
    ]
    for x, w, (t, s) in zip(xs, ws, hn, strict=True):
        d.node(x, top[2], w, hs[2], t, s)
    hm = top[2] + hs[2] // 2
    d.arrow(f"M406 {hm}H392")
    d.arrow(f"M582 {hm}H600")
    d.arrow(f"M774 {hm}H792")
    d.arrow(f"M966 {hm}H984")

    # pipeline
    d.node(
        X0,
        top[3],
        230,
        hs[3],
        "Miner",
        "GitHub GraphQL. Merged pull requests that close an issue and change a test.",
    )
    d.node(
        474,
        top[3],
        290,
        hs[3],
        "Validator: gold and empty gate",
        "Tests fail before the fix and pass after. Three runs drop flaky tests.",
    )
    d.node(794, top[3], 200, hs[3], "Dataset export", "Versioned JSONL, plus merge dates.")
    d.node(1024, top[3], 160, hs[3], "Rigor audit", "Re-runs the gate to catch drift.")
    pm = top[3] + hs[3] // 2
    d.arrow(f"M444 {pm}H472")
    d.arrow(f"M764 {pm}H792")
    d.arrow(f"M994 {pm}H1022")

    # data
    d.node(X0, top[4], 230, hs[4], "GitHub API", "Issues, pull requests, changed files.", "ext")
    d.node(
        474,
        top[4],
        290,
        hs[4],
        "Git mirrors",
        "One bare clone per repository. Source of every diff.",
        "store",
    )
    d.node(794, top[4], 200, hs[4], "Task set v0.2", "24 tasks, 3 languages.", "store")
    d.node(1024, top[4], 160, hs[4], "Postgres", "tasks, runs, results.", "store")
    pb = top[3] + hs[3]
    d.arrow(f"M329 {top[4]}V{pb + 2}", flow=False)
    d.arrow(f"M619 {top[4]}V{pb + 2}", flow=False)
    d.arrow(f"M894 {pb}V{top[4] - 2}", flow=False)
    return d.svg()


# ---------------------------------------------------------------------------------------------
def validation() -> str:
    d = Diagram(
        1200, 372, "Flow that turns a candidate pull request into a validated task or a logged rejection."
    )
    steps = [
        ("1  Candidate", "A merged pull request that closed an issue and changed a test."),
        ("2  Materialize", "git archive of the commit before the fix into a plain folder. No history."),
        ("3  Install", "The language adapter installs dependencies at the exact runtime version."),
        ("4  Red run", "Add only the pull request's tests. The target tests must fail."),
        ("5  Green run", "Apply the human fix. The same tests must now pass."),
        ("6  Derive sets", "fail_to_pass and pass_to_pass, from three runs. Flaky tests dropped."),
        ("7  Accept", "A schema-checked TaskInstance is written to the dataset."),
    ]
    for i, (t, s) in enumerate(steps):
        x = i * 175
        d.node(x, 30, 150, 156, t, s, "out" if i == 6 else "core")
        if i < 6:
            d.arrow(f"M{x + 150} 108H{x + 175}")
    d.arrow("M535 186V262", flow=False, dashed=True)
    d.arrow("M710 186V262", flow=False, dashed=True)
    d.text(548, 230, "otherwise", "dg-label")
    d.node(
        425,
        264,
        410,
        84,
        "Rejected, with a logged reason",
        "No failing test before the fix, tests still fail after it, or the install broke.",
        "warn",
    )
    d.note(
        0,
        226,
        388,
        122,
        "Compiled languages: if the new tests cannot compile before the fix, that counts as failing. Test names are read from the diff, and the green run still has to prove them.",
    )
    return d.svg()


def attempt() -> str:
    d = Diagram(
        1200, 500, "How one model attempt is produced in a private workspace, then scored on a clean rebuild."
    )
    d.text(0, 20, "The agent works here", "dg-lane")
    d.node(0, 36, 190, 118, "Task", "Issue text and the commit before the fix.", "store")
    d.node(
        230,
        36,
        230,
        118,
        "Private workspace",
        "A copy with its own throwaway git repo. None of the project's history.",
    )
    d.node(
        500,
        36,
        290,
        118,
        "Agent loop",
        "The model sees the issue and code. One shell command per turn, 40 turns, 15 minutes.",
    )
    d.node(830, 36, 170, 118, "Patch", "git diff of everything it changed.", "out")
    d.node(1030, 36, 170, 118, "Meter", "Tokens, cost and time are logged.", "ext")
    d.arrow("M190 95H228")
    d.arrow("M460 95H498")
    d.arrow("M790 95H828")
    d.arrow("M1000 95H1028", flow=False, dashed=True)

    d.text(48, 232, "Then scoring starts from scratch", "dg-lane")
    row = [
        ("Rebuild clean", "New copy of the commit before the fix. No .git."),
        ("Reset tests", "Any test file the agent touched is restored."),
        ("Apply patch", "Strict first, then fuzzy. A bad diff scores as not fixed."),
        ("Add hidden tests", "The project's real tests for this bug."),
        ("Run the suite", "In the sandbox, with a timeout."),
        ("Score", "Fixed only if every target test passes and nothing else breaks."),
    ]
    for i, (t, s) in enumerate(row):
        x = i * 200
        d.node(x, 248, 176, 132, t, s, "out" if i == 5 else "core")
        if i < 5:
            d.arrow(f"M{x + 176} 314H{x + 200}")
    d.arrow("M915 154V206H630V246", label="patch", lx=772, ly=198)
    d.arrow("M24 154V246", flow=False, dashed=True)
    d.note(
        0,
        404,
        1200,
        72,
        "Result: status (ok, patch_apply_failed, timeout or infra_error), resolved, per-test outcomes, cost, tokens and seconds. infra_error is our failure, not the model's, so it is left out of the score.",
    )
    return d.svg()


def adapters() -> str:
    d = Diagram(
        1200,
        500,
        "The language adapter seam: language-agnostic core, a four-method interface, three adapters.",
    )
    d.node(
        0,
        0,
        1200,
        80,
        "Core, with no language-specific code",
        "",
        "store",
        lines=[
            "pipeline (miner, validator, export), harness (eval runner, sandbox) and agent. Everything above the interface treats every language the same."
        ],
    )
    d.node(440, 112, 320, 52, "get_adapter(language)", "", "core", lines=[])
    d.arrow("M600 80V110", flow=False)
    d.node(220, 196, 760, 100, "LanguageAdapter interface", "", "core", lines=[])
    for i, m in enumerate(["detect_environment()", "install()", "run_tests()", "parse_results()"]):
        x = 240 + i * 184
        d.parts.append(
            f'<g class="dg-chip"><rect x="{x}" y="230" width="172" height="42" rx="3"/><text x="{x + 86}" y="256" text-anchor="middle">{esc(m)}</text></g>'
        )
    d.arrow("M600 164V194", flow=False)
    d.text(780, 144, "Adding Java took one line here and two schema allowlist entries.", "dg-label")
    cols = [
        (
            "TypeScript adapter",
            [
                "npm, pnpm or yarn, from the lockfile",
                "Exact Node version through nvm",
                "vitest or jest, JSON to a file",
                "Monorepo aware",
            ],
        ),
        (
            "Python adapter",
            [
                "pip, poetry, uv or pipenv detected",
                "Isolated uv venv per task",
                "pytest with a JSON report",
                "Exit code 4 means collection failed",
            ],
        ),
        (
            "Java adapter",
            [
                "Maven, or a repo's own Gradle wrapper",
                "One modern JDK builds every project",
                "Surefire and JUnit XML reports",
                "A compile failure is a real result",
            ],
        ),
    ]
    for i, (t, ls) in enumerate(cols):
        d.node(i * 412, 358, 376, 132, t, "", "core", lines=ls)
    d.arrow("M188 358V330H520V298", flow=False)
    d.arrow("M600 358V298", flow=False)
    d.arrow("M1012 358V330H680V298", flow=False)
    d.text(612, 350, "each adapter implements it", "dg-label")
    return d.svg()


def scaleout() -> str:
    d = Diagram(
        1200,
        470,
        "Kafka and Kubernetes job queue: producer, topic, three workers, idempotent writes to Postgres.",
    )
    d.node(0, 66, 180, 108, "Job producer", "One job per model, task and repeat.")
    d.node(230, 66, 200, 108, "Kafka topic", "ts-bench-jobs, 6 partitions, KRaft mode.")
    d.dashed_box(480, 30, 440, 176, "Kubernetes Deployment: 3 replicas, one consumer group")
    for i in range(3):
        d.node(
            496 + i * 138, 78, 126, 108, f"Worker {i + 1}", "", "core", lines=["Runs one job", "at a time"]
        )
    d.node(970, 66, 230, 108, "Postgres", "One row per run, task and repeat.", "store")
    d.arrow("M180 120H228")
    d.arrow("M430 120H478")
    d.arrow("M920 120H968")

    steps = [
        ("1  Pull a job", "Take one message from the topic."),
        ("2  Already done?", "Look up the key in Postgres. If present, skip."),
        ("3  Run it", "Agent, then the eval runner, in a sandbox."),
        ("4  Write once", "INSERT with ON CONFLICT DO NOTHING."),
        ("5  Commit the offset", "Only now does Kafka mark it done."),
    ]
    for i, (t, s) in enumerate(steps):
        x = i * 246
        d.node(x, 244, 216, 108, t, s, "out" if i == 4 else "core")
        if i < 4:
            d.arrow(f"M{x + 216} 298H{x + 246}")
    d.note(
        0,
        376,
        1200,
        82,
        "Key is (run_id, instance_id, repeat), the same key the sequential driver uses. If a pod dies between steps 3 and 5 the offset was never committed, so another pod picks the job up. Verified by force-killing a pod mid-job: 30 jobs gave exactly 30 rows, none lost, none duplicated.",
    )
    return d.svg()
