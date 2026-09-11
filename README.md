# Supply Chain Sparks

Automated supply-chain intelligence for **Saudi Arabia and the GCC**. The
desktop app fetches news from your sources around the clock, clusters
duplicates, has an AI editor score every story against an editorial rubric,
and writes publish-ready bilingual (English + Arabic) articles and LinkedIn
posts — with human approval before anything goes live.

```
sources → fetch → extract → cluster → LLM-judge → rank → draft EN+AR → approve → publish
```

## Download

Grab **`SupplyChainSparks-Setup.exe`** from the
[latest release](https://github.com/BasimBashir/supplychainsparks/releases)
and run it — no Python, Node or developer tools needed (Windows 10/11).
The app lives in the system tray; closing the window hides it to the tray.

A portable zip is attached to each release for machines without install
rights.

## How it works

| Piece | What it does |
|---|---|
| **Fetch engine** | RSS feeds, HTML listings and keyless web-search (topic) sources, robots.txt + per-domain politeness |
| **Judge** | An LLM scores every story on supply-chain relevance, Saudi/GCC relevance, market impact and novelty — a rubric, not keyword regexes |
| **Ranker** | Rubric + corroboration + source credibility + recency → high / medium / low bands |
| **Writer** | Article and LinkedIn post drafts in English and Arabic, with SEO metadata |
| **Fact-check** | Drafts are checked against the source record; flags must be resolved before publishing |
| **Publisher** | Commits the bilingual article to a GitHub content repo; the website rebuilds itself |

### Hybrid AI: cloud or fully local

- **Cloud** — [OpenRouter](https://openrouter.ai) (any vendor's model) or any
  OpenAI-compatible endpoint.
- **Local only** — [Ollama](https://ollama.com) on your own machine:
  **no API key, no cloud, no cost.** GPU is used automatically when present.

Source attribution (original article links) is kept in the local app and is
**never published**. LinkedIn posting is copy-paste by design.

## For developers

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q          # backend tests

cd dashboard
npm install
npm run dev                                 # dashboard (vite)
npx vitest run                              # frontend tests

# full release build (frontend + PyInstaller + Inno Setup installer):
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

Configuration lives in `settings.yaml`; secrets (API keys, git token)
belong in `secrets.yaml` inside the app's data folder
(`%LOCALAPPDATA%\SupplyChainSparks`) and are gitignored.

Website: [supplychainsparks.com](https://supplychainsparks.com)
