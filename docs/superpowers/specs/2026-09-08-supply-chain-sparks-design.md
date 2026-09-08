# Supply Chain Sparks — Design Spec

**Date:** 2026-09-08
**Status:** Approved (design review complete)
**Product:** AI-powered supply chain intelligence & publication platform for Saudi Arabia / the Middle East
**Domain:** supplychainsparks.com

---

## 1. Vision & Positioning

Supply Chain Sparks automates the daily workflow Zahid currently does by hand: collect supply-chain market intelligence → judge what matters → write publication-ready content → publish to LinkedIn and the web, with a Saudi/GCC lens.

The system collects news on a schedule (or on demand), stores it locally, deduplicates it, scores it the way a human editor would (LLM-judge with an editorial rubric), and presents a ranked editorial queue. A human selects stories; AI generates bilingual (EN + AR) website articles and LinkedIn posts; the human reviews, edits, approves, and publishes. AI does the research and heavy lifting; the human keeps editorial control.

Evolution path: v1 publication platform → v2 hosted multi-user + newsletter + research agents → v3 full intelligence platform (company/project/investment tracking, trends, research assistant). This spec covers v1 only.

## 2. Decision Log

| # | Decision | Choice |
|---|----------|--------|
| 1 | MVP scope | Pipeline + editorial dashboard **+ public blog** (supplychainsparks.com) from day 1 |
| 2 | Operator | Basim only in v1; data model & API layered so Zahid can be added later without rework |
| 3 | LLM strategy | Hybrid — local CPU LLM for bulk/offline work, API model for final published writing |
| 4 | Public site | Hosted Next.js app (Cloudflare Pages) |
| 5 | LinkedIn | Copy-paste with in-app preview (no API auto-posting in v1) |
| 6 | Language | **Bilingual English + Arabic** for all generated content |
| 7 | Sources | Free first (RSS + polite scraping); search/deep-research agent added in Phase 2 |
| 8 | Target hardware | **8–16 GB RAM, CPU-only, Windows 10/11** — design floor is 8 GB |
| 9 | Local app form | **Native Windows `.exe`** (installer + portable), tray-resident, non-technical-user-proof |
| 10 | Local stack | Python core + FastAPI + React dashboard in pywebview, packaged with PyInstaller |
| 11 | Scoring | **LLM-judge with editorial rubric** on every story — no regex/keyword relevance scoring. *Refines Decision 3: judging runs on the API tier by default; the local LLM is the fallback judge and offline-gist tier* |
| 12 | Source attribution | Shown in local app only; **never** in published site/LinkedIn content |

## 3. System Architecture

```
┌─ SupplyChainSparks.exe (local, tray-resident) ──────────────┐
│  pywebview window (Edge WebView2) → React dashboard         │
│              ⇅ HTTP (localhost, token)                       │
│  FastAPI local server                                        │
│  + APScheduler (fetch N×/day) + "Fetch Now"                  │
│                                                              │
│  PIPELINE                                                    │
│  Fetcher → Extractor → Deduplicator → Noise filter           │
│          → LLM-JUDGE (rubric scoring) → Ranker → Queue       │
│                                                              │
│  GENERATION (on selection)                                   │
│  API model → article EN/AR + LinkedIn EN/AR + SEO            │
│  → fact-check pass → human review → approve                  │
│                                                              │
│  STORAGE: SQLite + raw files (%LOCALAPPDATA%)                │
│  LLM: Ollama Qwen2.5-3B (optional local tier/fallback)       │
└──────────── git push (markdown) ─────────────────────────────┘
                     ↓
     Next.js site on Cloudflare Pages — supplychainsparks.com
```

Two artifacts, one design system: the local exe (pipeline + editorial dashboard) and the hosted Next.js public site. The site never depends on the local PC being on.

## 4. Pipeline

### 4.1 Fetcher
- Source registry in config (YAML, editable without rebuild):
  - **Google News RSS keyword queries** per topic: "Saudi logistics", "Red Sea shipping", "GCC warehousing", "Saudi ports", etc.
  - **Curated publication feeds**: Supply Chain Digest, Logistics Middle East, Gulf News, Aramco/Mawani/Ministry of Transport press rooms, etc.
  - **HTML pages** for sources without RSS (press-release listings).
- Politeness: robots.txt respected, per-domain rate limit, identifying User-Agent.
- Raw HTML/JSON saved to `data/raw/<date>/<hash>.{html,json}` **before any processing** (traceability).
- Per-source failure isolation: retry with backoff → mark source unhealthy → show in dashboard; never blocks other sources.

### 4.2 Extractor
- trafilatura (readability-style) → title, date, author, clean text, language.
- Discards non-articles (<150 words, navigation/list pages).

### 4.3 Deduplicator (cluster, don't delete)
- Tiered: normalized URL → fuzzy title match (rapidfuzz ≥ 90) → simhash on body text.
- Matches merge into a **story cluster**: highest-credibility source = primary; the rest = supporting sources.
- Corroboration (N independent outlets) feeds the composite score and content generation quality.
- The dashboard shows every source in a cluster ("Taken from: Reuters, Gulf News, Mawani") — **local-only record**; generation is hard-constrained to never name or link sources in published output.

### 4.4 Noise filter (plumbing, not judgment)
- Mechanical only: word count, language, obvious spam. No regex decides relevance.

### 4.5 LLM-Judge scoring (the core of the product)
Every deduplicated story is read and scored by an LLM acting as a junior editor.

**Input:** title + lead paragraph + first ~1,500 characters of the extracted body (bounded context keeps CPU/API cost per story constant).
**Output (JSON schema, validated):**
- `supply_chain_relevance` 0–10
- `saudi_gcc_relevance` 0–10
- `market_impact` 0–10
- `novelty` 0–10
- one-line **rationale per factor** (editor's-note style)
- `suggested_category`, 2-sentence `gist`

**Execution tiers (config switch, one click):**
- **Default: fast API model** (GLM-4-flash class) — ~100–200 stories/day, parallel calls, queue ready in 1–3 min, cost ≈ cents/day.
- **Fallback: local Ollama Qwen2.5-3B** — same schema, noisier scores, labeled "local judge" in UI. Used automatically when offline/no key.

**Consistency:** the rubric prompt is a versioned file with few-shot anchor examples (a 9-impact story, a 3, a 1) so scores mean the same thing daily. Tunable without rebuilding the exe.

### 4.6 Ranker (composite priority)
```
priority = w1·supply_chain_relevance + w2·saudi_gcc_relevance
         + w3·market_impact + w4·novelty          (judge rubric)
         + recency_decay + source_credibility
         + corroboration_bonus                    (mechanical signals)
```
Weights configurable. Score breakdown (per-factor rationale + mechanical components) stored and shown in the dashboard — every ranking is explainable.

### 4.7 Item lifecycle
`new → ranked → selected → generating → review → approved → published`, with `rejected`/`archived` reachable from any state. Every transition is timestamped (feeds the Published tab).

## 5. LLM Strategy

| Tier | Model | Jobs |
|------|-------|------|
| Local (optional) | Ollama Qwen2.5-3B-Instruct Q4 (~2 GB) | Fallback judge, gists when offline, language assist |
| API (configurable) | GLM / Claude frontier class | Primary judge, final article writing EN + AR, LinkedIn posts EN + AR, SEO fields, fact-check verdicts |

- **8 GB floor:** the app must run acceptably with no Ollama installed — local tier degrades gracefully; rules-of-thumb recency/credibility still apply; judge falls back to local only when present.
- API only runs on selected stories (+ per-story judging) → ≲ $1/day total.
- Prompt templates are versioned files on disk (editable without rebuild) — voice/tone tunable by editing text, not code.

## 6. Content Generation (bilingual)

From a selected story cluster (primary text + supporting gists):

| Format | Spec |
|--------|------|
| Website article EN | Headline, executive summary, "what happened", "why it matters for Saudi/GCC", key takeaways; 400–700 words |
| Website article AR | Native Arabic journalistic rewrite (not literal translation); same factual skeleton |
| LinkedIn post EN | Hook line, 3–5 insight lines, CTA question, hashtags; front-loads before "…see more" fold |
| LinkedIn post AR | Same structure, native Arabic |
| SEO block | Slug, meta description, tags (site article only) |

**Hard prompt constraints:** no source names, no external links, no invented numbers, dates, or names.

**Fact-check pass:** every claim (number/date/name) in generated output must map to a supporting sentence in the fetched material. Unverifiable claims are flagged; the review editor highlights them and **Approve stays disabled until each flag is resolved** (edit or explicitly confirm).

## 7. Editorial Dashboard (React, in-exe)

| Tab | Purpose |
|-----|---------|
| **Queue** | Ranked story cards: priority badge (🔴🟠🟢), score + judge rationale, category, corroboration count, age. Filters (category/priority/date). Multi-select → Generate |
| **Story detail** | Full clean text, all cluster sources (lock icon = local-only), score breakdown, gist, per-format generate buttons |
| **Review** | Side-by-side EN/AR markdown editors, inline fact-check flags (claim → source snippet), LinkedIn character counter, Approve gated on flag resolution |
| **Published** | Archive/audit trail: every published item with destination (site EN/AR, LinkedIn EN/AR), generated + published timestamps, live URL, re-copy buttons |

Status bar: last/next fetch, source health, LLM tier in use, Ollama detected. UI strings externalized so an Arabic UI can be added later. No local auth in v1 (localhost + token); `users`/`approvals` tables exist for the future hosted version.

## 8. Public Site & Publishing

- **Next.js (App Router) on Cloudflare Pages** (free tier, global CDN incl. KSA), domain supplychainsparks.com.
- Content as files in a git repo: `content/posts/<slug>/{en.md, ar.md, meta.json}` — version-controlled; site auto-deploys on push; ISR article/category pages; Arabic pages render RTL with an Arabic webfont; home shows **Latest articles + "Top stories this week"** (the week's highest-composite-priority published stories — no analytics dependency in v1).
- **Site publish flow:** Approve → exe commits markdown and pushes using **bundled dulwich (pure-Python git) over HTTPS with a stored access token** — no git installation, no SSH keys needed on the user's machine → Cloudflare builds → live URL lands in the Published tab (~1–2 min).
- **LinkedIn:** preview + one-click copy. Never auto-posts (API restrictions + manual control by design).
- The site never links out to original sources (per Decision 12).

## 9. Storage & Data Model

- **SQLite** (single file, `%LOCALAPPDATA%\SupplyChainSparks\`): `sources`, `fetch_runs`, `stories`, `clusters`/`story_sources`, `judge_scores`, `generations`, `fact_flags`, `publications`, `users`, `settings`.
- **Raw files:** `%LOCALAPPDATA%\SupplyChainSparks\data\raw\<date>\<hash>.{html,json}` + `data\processed\`.
- **Key property:** the DB is fully re-derivable from raw files — wipe and replay with new scoring config/prompt versions at any time.

## 10. Packaging, Scheduling, First Run

- PyInstaller one-folder build → Inno Setup installer (bootstraps Edge WebView2 if missing on Windows 10) + portable zip. Tray icon; window close = background operation. Single-instance lock. Rotating log file. Config in `%APPDATA%`.
- Fetch schedule configurable (default 4×/day) + Fetch Now.
- **First-run wizard:** check/install Ollama + pull model (optional, with clear "works without it" messaging), API key entry, content-repo connection (HTTPS URL + access token), schedule choice.

## 11. Error Handling

- Per-source fetch failures isolated (retry/backoff → unhealthy flag → dashboard).
- Ollama absent/offline → local tier off; judge falls back per config; UI states which tier scored the queue.
- Invalid API key → generation blocked with clear message; scoring degrades to local judge.
- Git push failure → publication queued and retried; never lost.
- SQLite corruption → rebuild from raw files.
- Judge output schema violation → single retry with stricter instruction, then story flagged "unscored" (still visible, bottom of queue).

## 12. Testing

- **pytest:** extractor, dedup, composite scoring, cluster merge — against a golden fixture set of recorded RSS/HTML (no network in CI).
- **Prompt contract tests:** judge output validates against the JSON schema; generation output contains no source names/links (automated check).
- **E2E happy path script:** fetch (recorded) → judge (mock) → generate (mock) → publish (to a temp git repo), asserting artifacts.
- Dashboard: light component tests; manual review primary.

## 13. Constraints & Non-Goals (v1)

- **Must:** run on 8 GB RAM CPU-only Windows 10/11; work without Ollama; never require the local PC for the public site to stay up; no external links in published content.
- **Not in v1:** LinkedIn API auto-posting, hosted/multi-user dashboard, newsletter, embeddings/semantic dedup, web-search/deep-research agent, intelligence dashboards, payment/subscription. All are Phase 2/3 (Section 14).

## 14. Roadmap

- **Phase 1 — this spec:** pipeline + LLM-judge queue + dashboard + bilingual generation + site publishing + LinkedIn copy.
- **Phase 2:** hosted dashboard for Zahid (multi-user approvals), newsletter, semantic dedup/search via embeddings, web-search/deep-research agent for gap-filling.
- **Phase 3:** intelligence platform — company/project/investment trackers, trend dashboards, AI research assistant over the accumulated archive.

## 15. Success Criteria

1. A full daily cycle — fetch → ranked queue → 2–3 bilingual stories approved and live — takes ≤ 30 minutes of human time (vs. hours today).
2. Queue rankings feel like a human editor's ordering (judged by Basim/Zahid spot checks).
3. Published articles pass fact-check with zero unresolved flags; no source links ever leak.
4. The exe installs and runs on a clean 8 GB Windows machine with no developer tools present.
