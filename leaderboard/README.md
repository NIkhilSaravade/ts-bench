# Leaderboard site (T10)

A React 19 + Vite + Tailwind 4 site, written to match the design language of the sibling
[`llm-serve`](https://github.com/NIkhilSaravade/LLM-serve) report: the same shell (fixed sidebar with
scroll progress and a dark/light toggle), the same three fonts (Bricolage Grotesque, Instrument Sans,
JetBrains Mono), the same motion library and the same interactive-diagram approach (click a component to
explain it, trace one request through the map, replay a state machine). The palette is deliberately
different (graphite-teal and aqua instead of ink-blue and lime) so the two read as siblings, not twins.

**Every number on the page is generated** from `data/results.json`, which is exported from the raw run
files. Nothing is typed in by hand except the fixed harness budget (40 turns, 15 minutes, from
`docs/fairness_contract.md`).

## Layout

| Path | What it is |
|---|---|
| `site-src/` | The source: `src/components`, `src/content`, `src/styles.css`, `public/`. |
| `site/` | The **built** output. Committed, so Cloudflare Pages serves it with no build step. |
| `data/results.json` | The exported real results (committed, 13 KB). |
| `../scripts/export_leaderboard_data.py` | Raw `results/*.jsonl` to `data/results.json`. |

Content lives in `site-src/src/content/`: `architecture.ts` (the system map), `seam.ts` (language
adapters), `flows.ts` (task validation, scoring steps, job queue), `problems.ts` (the debugging log). Each
claim there comes from `docs/ts-bench-task-board.md` or `docs/step7-real-model-run.md`.

## Update the numbers, then rebuild

```bash
# from the repo root, in Ubuntu/WSL
python3 scripts/export_leaderboard_data.py        # needs the (gitignored) raw results/*.jsonl
cd leaderboard/site-src
export npm_config_workspaces=false                 # this machine's global ~/.npmrc has workspaces=true
npm ci                                             # first time only
npm run build                                      # typechecks, then writes ../site
git add ../site ../data                            # commit the built site
```

`npm run dev` starts a dev server with hot reload.

## Deploy to Cloudflare Pages

The Pages project should have: framework preset **None**, build command **empty**, build output
directory **`leaderboard/site`**. Every push to `main` then redeploys the committed `site/` folder.
`site/_headers` sets a strict content-security policy (same-origin script, style and font only, no
third-party requests; fonts are bundled, not loaded from Google), so no inline script exists.

For a custom domain, add it under the Pages project's Custom domains. `llm-serve` lives on a subdomain of
the same domain, so a subdomain such as `ts-bench.<your-domain>` keeps the two consistent. If you use a
different address, change `VITE_SITE_URL` in `site-src/.env.production` and rebuild.

## Notes and known limits

- Verified in headless Edge (desktop 1440 px, a 500 px phone layout, dark and light themes) under the real
  security headers. Not tested on real phones, Safari or Firefox.
- Motion respects `prefers-reduced-motion`. The attempt field has a fallback timer so it can never stay
  hidden if the scroll-visibility signal does not arrive.
- No social-share (Open Graph) image yet. `llm-serve` generates one with Playwright; that step was left out
  to keep this build's dependencies small.
- Keyboard users get the diagram content as focusable nodes with the same detail panel, and every figure
  also exists in the tables.
