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

## First run — Setup

Open the app and go to **Setup**. Everything below is also configurable there;
the raw values live in `secrets.yaml` next to your settings file (never
committed) and override `settings.yaml`.

### 1. Engine — Cloud API or Local only

Two cards choose where **all** AI work happens (scoring, writing, fact-checking):

- **☁️ Cloud API** — best quality and speed. Needs an API key; costs a few
  cents/day. Default endpoint is GLM; any OpenAI-compatible provider works
  (edit `judge.api.base_url` in `settings.yaml`).
- **🖥️ Local only · Ollama** — the full bypass: **no API key, no cloud, no
  cost**. Everything runs on this PC through Ollama.

To use local mode:
1. Install Ollama from ollama.com.
2. Pull a model: `ollama pull qwen2.5:3b` (or any model you prefer).
3. Have Ollama running (`ollama serve`, or the desktop app).
4. In Setup, pick **Local only** and save.

Expect noticeably slower generation and lower polish on CPU — that is the
trade for a fully offline pipeline. Switch back to Cloud anytime.

### 2. Models

- **Cloud model** — the model name sent with every cloud request
  (default `glm-4-flash`). Change it to use a stronger/cheaper model from your
  provider, e.g. `glm-4-plus`.
- **Ollama model** — the model name your local Ollama must serve
  (default `qwen2.5:3b`). It must be pulled locally (`ollama pull <name>`).

### 3. Website publishing — what is the content repo?

The **content repo** is a plain GitHub repository that stores your published
articles as files:

```
content/posts/saudi-port-expansion-2026/
├── en.md       ← English article (markdown)
├── ar.md       ← Arabic article (markdown)
└── meta.json   ← title, description, category, tags, timestamps
```

It is the **bridge between the app and the website**:

```
desktop app ──commit──▶ GitHub content repo ──auto-build──▶ supplychainsparks.com
```

When you click **Publish to website**, the app commits the story's files into
this repository and pushes. The website is built directly from the repo, so it
rebuilds itself about a minute after every publish — and since the articles
live in GitHub, **the site stays up even when your PC is off**.

Setup:
1. Create an empty GitHub repository (e.g. `sparks-content`).
2. Create a fine-grained personal access token with **Contents: Read and
   write** access to it.
3. Paste the repo URL + token into Setup.

The website itself (Plan 3) connects this repo to Cloudflare Pages — same
repository, nothing extra to run.

### 4. Schedule

Hours between automatic fetches (default 6). `0` disables scheduling — you
fetch manually with **Fetch now**.

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

### Sources tab — manage what gets fetched

The **Sources** tab lists every source the engine fetches: name, type
(RSS/HTML/web search), health, credibility, and whether it's enabled. Use it to:

- **Add a source** — name, type, URL. Credibility (0–1) feeds the ranking;
  a category hint (e.g. `ports-shipping`) helps the judge. For HTML pages,
  a link pattern (regex, default `press|news|article`) decides which links
  count as stories. Adding a URL that already exists updates it instead of
  duplicating.
- **Add a web search topic** — type **Web search (topic)** and type any topic
  (`"Red Sea" shipping disruptions`, `Saudi port expansions`, …). Every fetch
  cycle runs a keyless DuckDuckGo news search for the topic and treats the
  results like any other source — no API key, and it works in local-only
  mode. Add as many topics as you want. Search results carry a snippet: if
  an article page blocks our fetcher (robots, paywall, dead link), the story
  is judged from the snippet instead of being dropped.
- **Disable / enable** — a disabled source stays in the list but is skipped by
  every fetch (useful when a feed goes bad). Re-enable the same way.

The first app run seeds six default sources (The Loadstar, Splash247,
gCaptain, FreightWaves, Container News, Argaam) — all verified to allow our
bot. Closing the window with the **X button hides the app to the tray** — it
keeps fetching on schedule. Tray → **Open Dashboard** (or launching the exe
again) brings the window back; tray → **Quit** is the only way the app exits.

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
- In **Cloud** mode, if the API key is missing or a request fails, scoring and
  generation fall back to Ollama when it is running; otherwise stories are
  marked `unscored` — the queue still works.
- In **Local only** mode nothing ever leaves this PC.
