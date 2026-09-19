# Leaderboard site (T10)

A static site: plain HTML, CSS and a little JavaScript. **No framework and no npm step**, so
Cloudflare Pages can serve the `site/` folder as it is.

Every number on the page comes from `data/results.json`, which is produced from the raw run files.
Nothing is typed in by hand except the fixed harness budget (40 turns, 15 minutes) and one note about
the separate LangGraph experiment; both are labelled with their source in `build.py`.

## Update the numbers and rebuild

```bash
# from the repo root, in Ubuntu/WSL
python3 scripts/export_leaderboard_data.py   # raw results/*.jsonl -> leaderboard/data/results.json
python3 leaderboard/build.py                 # data + src/ -> leaderboard/site/
```

`results/oss_leaderboard_run1.jsonl` is large and gitignored, so the export only works on a machine that
has it. `data/results.json` (13 KB) is committed, so `build.py` works anywhere without it.

## Preview locally

```bash
cd leaderboard/site && python3 -m http.server 8765
# open http://localhost:8765  (also works from Windows browsers)
# ?group=repo or ?group=result opens the squares grouped that way
```

## Files

| Path | What it is |
|---|---|
| `src/template.html` | Page structure and copy. `{{placeholders}}` are filled by `build.py`. |
| `src/style.css`, `src/app.js` | Styling and the interactive field of attempts. |
| `build.py` | Fills the template, builds the tables, tech stack, build log and task matrix, writes `site/`. Holds the hand-written stack, phase and "hard problems" content, each sourced from the task board. |
| `diagrams.py` | The five architecture diagrams, drawn as inline SVG by code (system layers, task validation gate, one attempt, language adapter seam, Kafka/Kubernetes queue). Edit here to change a diagram. |
| `data/results.json` | The exported real numbers (committed). |
| `site/` | The built site. This is the folder to deploy. |

## Deploy to Cloudflare Pages

Two ways. Neither has been done yet: nothing is published.

**A. Connect the GitHub repo (recommended; redeploys on every push)**

1. Cloudflare dashboard, Workers & Pages, Create, Pages, Connect to Git, pick `NIkhilSaravade/ts-bench`.
2. Framework preset: **None**. Build command: leave **empty**. Build output directory: `leaderboard/site`.
3. Save and deploy. You get a `*.pages.dev` address.

**B. Upload directly**

```bash
npx wrangler pages deploy leaderboard/site --project-name ts-bench
```

**Then attach your domain**

1. In the Pages project: Custom domains, Set up a custom domain, enter it (for example `bench.yourdomain.com`
   or the bare domain).
2. If the domain's DNS is already on Cloudflare, it adds the record for you. If not, add the `CNAME` it
   shows at your DNS provider (or move the domain's nameservers to Cloudflare).
3. Wait for the certificate to issue (usually minutes), then open the site over `https`.

`site/_headers` sets basic security headers and a one-hour cache on `/assets/*`. If you change CSS or JS
and want visitors to see it sooner, rename the files or shorten that cache line.

## Notes and known limits

- Fonts (Geist, Geist Mono, Newsreader) load from Google Fonts. If that is blocked the page falls back
  to system fonts and still works.
- Screenshots during development were taken with headless Edge at desktop width and at a true 390 px
  phone width. The page fits a phone with no sideways scrolling. It has not been tested on real devices,
  Safari, or Firefox.
- The tooltip on the squares works with a mouse or a tap. Keyboard users get the same information from
  the table and the task matrix, which are real HTML tables.
- Motion respects `prefers-reduced-motion`: with it on, squares appear in place and nothing animates.
- There is no social-share image yet.
