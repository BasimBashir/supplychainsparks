# Using Supply Chain Sparks (Desktop App)

## Where the app is

- **Dev build (ready now):** `dist\SupplyChainSparks\SupplyChainSparks.exe` — double-click to run.
- **Installer (for another PC):** from the repo root run
  `powershell -ExecutionPolicy Bypass -File scripts\build.ps1`
  (set `INNO_SETUP_PATH` to your Inno Setup folder to also produce
  `dist\SupplyChainSparks-Setup.exe`). Install on any Windows 10/11 box — no
  Python, no git, no developer tools needed on that machine.

The app lives in the **system tray** (⚡-ish teal diamond icon). Closing the
window keeps it running in the background. **Quit** from the tray menu.

## First run — Setup (Settings tab)

Open the app and go to **Settings**:

1. **API key** — the writer/judge model. Default endpoint is GLM (`glm-4-flash`,
   any OpenAI-compatible provider works — edit `judge.api` in `settings.yaml`).
   Cost is a few cents/day.
2. **Content repo URL + Git token** — a GitHub repo the app will publish articles
   into (e.g. `https://github.com/<org>/<content-repo>.git` + a fine-grained PAT
   with Contents: Read and write). The public website (Plan 3) deploys from this
   repo on every push.
3. **Fetch interval** — hours between automatic fetches (default 6; `0` = manual only).
4. **Ollama** (optional) — if `ollama serve` with `qwen2.5:3b` is running, it shows ✓
   and becomes the fallback judge when offline. Everything works without it.

Secrets are stored in `secrets.yaml` next to your settings file — never committed.

## Daily workflow

1. **Collect** — happens automatically on schedule (+ an immediate fetch at app
   start). Or tray → **Fetch Now**. Roughly 100–200 stories get fetched,
   deduplicated, and scored by the LLM-judge like an editor would.
2. **Queue tab** — ranked story cards: 🔴 high / 🟠 medium / 🟢 low, priority score,
   judge's rationale ("why it ranked"), corroboration count. Filter by band.
   Click **Select** (or **Open**) on stories worth publishing.
3. **Story detail** — full judge scorecard, gist, and all sources
   (🔒 local-only record — never published).
   Buttons: **Generate articles (EN+AR)** and **Generate LinkedIn (EN+AR)**.
   Generation takes ~30–60s (API model).
4. **Review tab** — open the story: side-by-side EN / AR (RTL) editors.
   - Edit freely, **Save**.
   - **Fact-check** each article: claims are checked against the fetched source
     text; unsupported claims appear as ⚠ flags. **Approve stays disabled until
     every flag is resolved** (resolve = confirm, or edit the text and re-check).
   - **Approve** → **Publish to site** (commits `en.md`/`ar.md`/`meta.json` to the
     content repo; the website goes live on the next deploy), and/or **Copy** a
     LinkedIn post (EN or AR) and **Mark copied** — LinkedIn is always pasted
     manually by design.
5. **Published tab** — the archive: everything published, destination, live URL,
   timestamps.

## Power-user CLI

With the repo venv active (`.venv\Scripts\activate`):

```
sparks init            # seed the 10 default sources
sparks fetch           # run a full cycle now
sparks queue -n 10     # show the ranked queue
sparks queue --band high
sparks sources list    # health of every source
sparks replay          # rebuild everything from raw files (keeps judge verdicts)
```

## Where your data lives

`%LOCALAPPDATA%\SupplyChainSparks\` — `SupplyChainSparks.db` (SQLite),
`raw\` (every fetched page, for replay/audit), `logs\sparks.log` (rotating),
`content-repo\` (local clone of the publishing repo).

## Notes & limits (v1)

- The public website (supplychainsparks.com rendering) is Plan 3 — the repo the
  app publishes into is the input side of it.
- LinkedIn auto-posting is deliberately not included (API restrictions);
  copy-paste with preview is the v1 flow.
- If the API key is missing, scoring falls back to Ollama (if running) and
  stories may be marked `unscored` — the queue still works.
