# Supply Chain Sparks — Plan 3: Public Website Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `supplychainsparks.com` — a bilingual (EN default / AR RTL) Next.js static site that renders articles from the content repo written by Plan 2's publisher, with home (latest + top stories this week), article pages, category pages, and SEO metadata; deployed on Cloudflare Pages.

**Architecture:** Fully static (`output: "export"`): content is read at build time from `content/posts/<slug>/{en.md, ar.md, meta.json}` — every publish push triggers a Cloudflare Pages rebuild, so no server, no database, and the site never depends on the local PC. `site/lib/content.js` is the only place that touches the filesystem; pages consume it. Arabic pages render under `/ar/post/[slug]` with `dir="rtl"`.

**Tech Stack:** Next.js 14 (App Router, static export), React 18, Tailwind CSS, `marked` for markdown. Tests: vitest (node environment, fs-based — no network).

**Spec:** `docs/superpowers/specs/2026-09-08-supply-chain-sparks-design.md` §8
**Depends on:** the content contract (below) — written by Plan 2 Task 8.

## Global Constraints

- **Content contract (verbatim from Plan 2 — do not diverge):**
  ```
  content/posts/<slug>/en.md      # English body, markdown, no H1
  content/posts/<slug>/ar.md      # Arabic body, markdown, no H1
  content/posts/<slug>/meta.json  # {
                                   #   "slug": "saudi-port-expansion-2026",
                                   #   "title": "...", "titleAr": "...",
                                   #   "description": "...", "descriptionAr": "...",
                                   #   "category": "ports-shipping",
                                   #   "tags": ["Jeddah", "Mawani"],
                                   #   "publishedAt": "2026-09-08T14:30:00Z",
                                   #   "priority": 91.2
                                   # }
  ```
- Static export only (`output: "export"`); no server runtime, no ISR. Posts missing `ar.md` render EN-only with an AR notice ("النسخة العربية قريبًا" if `titleAr` empty, else AR page with fallback note).
- **Published pages never link to original news sources** (spec Decision 12). The renderer adds `target="_blank" rel="noreferrer"` only for internal absolute links; external links should not exist — render-time sanitization strips `http(s)://` anchors to plain text defensively.
- No network in tests. `next build` (which needs npm registry at install time only) is the integration check.
- Sample content lives in `site/test-content/` for tests and `content/` (repo root) receives real posts from Plan 2; until the publisher runs, `content/` holds two committed sample posts so the site builds.
- Fonts: Google Fonts `<link>` tags in the layout (loaded by visitors' browsers, not at build).
- TDD: red → green → commit per task.

## File Structure

```
supplychainsparks/
├── content/posts/                          # real content (Plan 2 writes here)
│   ├── saudi-port-expansion-2026/{en.md,ar.md,meta.json}     # committed samples
│   └── red-sea-shipping-update-2026/{en.md,ar.md,meta.json}
└── site/
    ├── package.json  next.config.mjs  tailwind.config.js  postcss.config.js
    ├── app/
    │   ├── layout.js  page.js  not-found.js
    │   ├── globals.css
    │   ├── post/[slug]/page.js             # English article
    │   ├── ar/post/[slug]/page.js          # Arabic article (RTL)
    │   ├── category/[slug]/page.js
    │   ├── sitemap.js  robots.js
    │   └── ar/layout.js                    # dir=rtl + ar font wrapper
    ├── components/PostCard.jsx  TopStories.jsx  Nav.jsx
    ├── lib/content.js                      # loadPosts, getPost, topStories, categories
    └── tests/content.test.js
```

**Interface contract:**
- `site/lib/content.js` — `loadPosts(contentDir?) -> Post[]`, `getPost(slug, contentDir?) -> Post | null`, `topStories(weekCount=1, n=5, contentDir?) -> Post[]`, `categories(contentDir?) -> {name, count}[]`
- `Post` shape: `{ slug, title, titleAr, description, descriptionAr, category, tags, publishedAt: Date, priority, enMd, arMd | null }`

---

### Task 1: Scaffold + sample content

**Files:**
- Create: `site/package.json`, `site/next.config.mjs`, `site/tailwind.config.js`, `site/postcss.config.js`, `site/app/globals.css`, root `content/posts/...` samples
- Test: none yet (scaffold only — verified by Task 2's tests and the Task 7 build)

- [ ] **Step 1: Scaffold config files**

`site/package.json`:

```json
{
  "name": "supplychainsparks-site",
  "private": true,
  "version": "0.1.0",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "test": "vitest run"
  },
  "dependencies": {
    "marked": "^12.0.0",
    "next": "^14.2.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.3",
    "vitest": "^2.0.0",
    "@vitejs/plugin-react": "^4.3.0"
  }
}
```

`site/next.config.mjs`:

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  trailingSlash: false,
};
export default nextConfig;
```

`site/tailwind.config.js`:

```js
export default {
  content: ["./app/**/*.{js,jsx}", "./components/**/*.{js,jsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

`site/postcss.config.js`:

```js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } };
```

`site/app/globals.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body { @apply bg-slate-950 text-slate-100; }
.prose-ar { font-family: "Noto Kufi Arabic", "IBM Plex Sans Arabic", system-ui, sans-serif; }
```

- [ ] **Step 2: Sample posts**

`content/posts/saudi-port-expansion-2026/meta.json`:

```json
{
  "slug": "saudi-port-expansion-2026",
  "title": "Jeddah Port Pushes Major Capacity Expansion",
  "titleAr": "ميناء جدة يطلق توسعة كبرى للطاقة الاستيعابية",
  "description": "Container handling capacity at Jeddah Islamic Port is set for a significant jump.",
  "descriptionAr": "طاقة مناولة الحاويات في ميناء جدة الإسلامي تستعد لقفزة كبيرة.",
  "category": "ports-shipping",
  "tags": ["Jeddah", "containers"],
  "publishedAt": "2026-09-08T14:30:00Z",
  "priority": 91.2
}
```

`content/posts/saudi-port-expansion-2026/en.md` — two paragraphs of neutral sample prose (no source references, no links). `ar.md` — Arabic equivalent. Second post `red-sea-shipping-update-2026/` — same shape, category `ports-shipping`, lower priority (62.0), `publishedAt` six days earlier.

- [ ] **Step 3: Install and verify dev server boots**

```bash
cd site && npm install
```

- [ ] **Step 4: Commit**

```bash
git add site/ content/
git commit -m "chore: site scaffold and sample content"
```

---

### Task 2: Content library

**Files:**
- Create: `site/lib/content.js`, `site/tests/content.test.js`, `site/vitest.config.js`

**Interfaces:**
- Produces: the four exported functions + `Post` shape above. `contentDir` defaults to `<repo root>/content/posts` resolved relative to the module (`path.resolve(__dirname, "../../content/posts")`).

- [ ] **Step 1: Write the failing tests**

`site/vitest.config.js`:

```js
import { defineConfig } from "vitest/config";
export default defineConfig({ test: { environment: "node" } });
```

`site/tests/content.test.js`:

```js
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { test, expect, beforeAll, afterAll } from "vitest";
import { loadPosts, getPost, topStories, categories } from "../lib/content.js";

let dir;
const now = new Date();
const daysAgo = (n) => new Date(now.getTime() - n * 86400000).toISOString();

function post(slug, meta, en = "EN body", ar = "AR body") {
  const base = path.join(dir, slug);
  mkdirSync(base, { recursive: true });
  writeFileSync(path.join(base, "meta.json"), JSON.stringify(meta), "utf8");
  writeFileSync(path.join(base, "en.md"), en, "utf8");
  if (ar) writeFileSync(path.join(base, "ar.md"), ar, "utf8");
}

beforeAll(() => {
  dir = path.join(tmpdir(), `sparks-content-${Date.now()}`);
  mkdirSync(dir, { recursive: true });
  post("high-and-fresh", { slug: "high-and-fresh", title: "T1", titleAr: "ت1",
    description: "d", descriptionAr: "د", category: "ports-shipping", tags: [],
    publishedAt: daysAgo(1), priority: 91 });
  post("low-and-old", { slug: "low-and-old", title: "T2", titleAr: "ت2",
    description: "d", descriptionAr: "د", category: "warehousing", tags: [],
    publishedAt: daysAgo(10), priority: 55 });
  post("en-only", { slug: "en-only", title: "T3", titleAr: "", description: "d",
    descriptionAr: "", category: "ports-shipping", tags: [], publishedAt: daysAgo(2),
    priority: 70 }, "EN only body", null);
});

afterAll(() => rmSync(dir, { recursive: true, force: true }));

test("loadPosts parses contract and sorts by date desc", () => {
  const posts = loadPosts(dir);
  expect(posts.map((p) => p.slug)).toEqual(["high-and-fresh", "en-only", "low-and-old"]);
  expect(posts[0].publishedAt).toBeInstanceOf(Date);
  expect(posts[2].arMd).toBeNull();
});

test("getPost returns null for unknown slug", () => {
  expect(getPost("nope", dir)).toBeNull();
  expect(getPost("en-only", dir).enMd).toBe("EN only body");
});

test("topStories = this week sorted by priority", () => {
  const top = topStories(1, 5, dir);
  expect(top.map((p) => p.slug)).toEqual(["high-and-fresh", "en-only"]);  // 10d old excluded
  expect(top[0].priority).toBe(91);
});

test("categories counts", () => {
  expect(categories(dir)).toEqual([
    { name: "ports-shipping", count: 2 }, { name: "warehousing", count: 1 }]);
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd site && npm test
```
Expected: FAIL — cannot resolve `../lib/content.js`.

- [ ] **Step 3: Implement `site/lib/content.js`**

```js
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)),
                                 "../../content/posts");

export function loadPosts(contentDir = DEFAULT_DIR) {
  if (!existsSync(contentDir)) return [];
  return readdirSync(contentDir, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => {
      const base = path.join(contentDir, d.name);
      const metaPath = path.join(base, "meta.json");
      if (!existsSync(metaPath)) return null;
      const meta = JSON.parse(readFileSync(metaPath, "utf8"));
      const read = (f) => (existsSync(path.join(base, f))
        ? readFileSync(path.join(base, f), "utf8") : null);
      return { ...meta, publishedAt: new Date(meta.publishedAt),
               enMd: read("en.md"), arMd: read("ar.md") };
    })
    .filter(Boolean)
    .sort((a, b) => b.publishedAt - a.publishedAt);
}

export function getPost(slug, contentDir = DEFAULT_DIR) {
  return loadPosts(contentDir).find((p) => p.slug === slug) ?? null;
}

export function topStories(weekCount = 1, n = 5, contentDir = DEFAULT_DIR) {
  const cutoff = Date.now() - weekCount * 7 * 86400000;
  return loadPosts(contentDir)
    .filter((p) => p.publishedAt.getTime() >= cutoff)
    .sort((a, b) => b.priority - a.priority)
    .slice(0, n);
}

export function categories(contentDir = DEFAULT_DIR) {
  const counts = {};
  for (const p of loadPosts(contentDir)) counts[p.category] = (counts[p.category] || 0) + 1;
  return Object.entries(counts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd site && npm test
```
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add site/lib/ site/tests/ site/vitest.config.js
git commit -m "feat: site content library"
```

---

### Task 3: Layout, nav, home page

**Files:**
- Create: `site/app/layout.js`, `site/app/page.js`, `site/components/Nav.jsx`, `site/components/PostCard.jsx`, `site/components/TopStories.jsx`
- Test: verified via Task 5 build; unit tests stay in content lib (rendering is static).

- [ ] **Step 1: `site/app/layout.js`**

```js
import "./globals.css";
import Nav from "../components/Nav.jsx";

export const metadata = {
  title: { default: "Supply Chain Sparks", template: "%s · Supply Chain Sparks" },
  description: "AI-powered supply chain intelligence for Saudi Arabia and the GCC.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;600&display=swap" rel="stylesheet" />
      </head>
      <body className="min-h-screen flex flex-col">
        <Nav />
        <main className="flex-1 w-full max-w-3xl mx-auto px-4 py-8">{children}</main>
        <footer className="text-sm text-slate-400 py-6 text-center border-t border-slate-800">
          © {new Date().getFullYear()} Supply Chain Sparks — supply chain intelligence, Saudi Arabia & GCC
        </footer>
      </body>
    </html>
  );
}
```

- [ ] **Step 2: `site/components/Nav.jsx` and cards**

```jsx
export default function Nav() {
  return (
    <header className="border-b border-slate-800">
      <div className="max-w-3xl mx-auto px-4 py-4 flex items-baseline justify-between">
        <a href="/" className="text-xl font-bold text-amber-400">⚡ Supply Chain Sparks</a>
        <nav className="space-x-4 text-sm text-slate-300">
          <a href="/" className="hover:text-white">Latest</a>
          <a href="/category/ports-shipping" className="hover:text-white">Ports & Shipping</a>
          <a href="/category/logistics" className="hover:text-white">Logistics</a>
        </nav>
      </div>
    </header>
  );
}
```

```jsx
export default function PostCard({ post }) {
  return (
    <a href={`/post/${post.slug}`} className="block py-4 border-b border-slate-800 group">
      <div className="text-xs text-slate-400 mb-1">
        {post.publishedAt.toISOString().slice(0, 10)} · {post.category}
      </div>
      <h2 className="text-lg font-semibold group-hover:text-amber-400">{post.title}</h2>
      <p className="text-sm text-slate-400 mt-1">{post.description}</p>
      {post.titleAr && (
        <a href={`/ar/post/${post.slug}`} className="text-xs text-slate-500 hover:text-amber-400">
          اقرأ بالعربية
        </a>
      )}
    </a>
  );
}
```

```jsx
import PostCard from "./PostCard.jsx";

export default function TopStories({ posts }) {
  if (!posts.length) return null;
  return (
    <section className="mb-10">
      <h2 className="text-sm uppercase tracking-wide text-amber-400 mb-2">Top stories this week</h2>
      {posts.map((p) => <PostCard key={p.slug} post={p} />)}
    </section>
  );
}
```

- [ ] **Step 3: `site/app/page.js`**

```js
import PostCard from "../components/PostCard.jsx";
import TopStories from "../components/TopStories.jsx";
import { loadPosts, topStories } from "../lib/content.js";

export default function Home() {
  const posts = loadPosts();
  const top = topStories(1, 5);
  const latest = posts.filter((p) => !top.some((t) => t.slug === p.slug));
  return (
    <>
      <h1 className="text-2xl font-bold mb-6">Latest</h1>
      <TopStories posts={top} />
      {latest.map((p) => <PostCard key={p.slug} post={p} />)}
    </>
  );
}
```

- [ ] **Step 4: Verify in dev**

```bash
cd site && npm run dev   # open http://localhost:3000, confirm posts listed
```

- [ ] **Step 5: Commit**

```bash
git add site/app/ site/components/
git commit -m "feat: site layout and home page"
```

---

### Task 4: Article pages (EN + AR RTL) with markdown + link sanitization

**Files:**
- Create: `site/app/post/[slug]/page.js`, `site/app/ar/post/[slug]/page.js`, `site/app/ar/layout.js`, `site/lib/render.js`
- Test: `site/tests/render.test.js`

**Interfaces:**
- Produces: `renderMarkdown(md) -> html string` — markdown → HTML **with external links neutralized** (any `<a href="http...">` becomes its plain text; internal relative links kept, opened in a new tab).

- [ ] **Step 1: Write the failing test**

`site/tests/render.test.js`:

```js
import { test, expect } from "vitest";
import { renderMarkdown } from "../lib/render.js";

test("renders basic markdown", () => {
  expect(renderMarkdown("## Head\n\nBody with **bold**.")).toContain("<h2>Head</h2>");
  expect(renderMarkdown("Body with **bold**.")).toContain("<strong>bold</strong>");
});

test("external links are neutralized to plain text", () => {
  const html = renderMarkdown("Read [this report](https://example.com/x) now.");
  expect(html).not.toContain("<a");
  expect(html).toContain("this report");
});

test("relative links are kept", () => {
  const html = renderMarkdown("See [other post](/post/other).");
  expect(html).toContain('href="/post/other"');
  expect(html).toContain('target="_blank"');
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd site && npm test
```
Expected: render tests FAIL (module missing).

- [ ] **Step 3: Implement `site/lib/render.js`**

```js
import { marked } from "marked";

export function renderMarkdown(md) {
  const raw = marked.parse(md ?? "");
  return raw.replace(/<a\s+href="([^"]*)"[^>]*>(.*?)<\/a>/gs, (m, href, text) => {
    if (/^https?:\/\//i.test(href)) return text;           // external -> plain text
    return `<a href="${href}" target="_blank" rel="noreferrer">${text}</a>`;
  });
}
```

- [ ] **Step 4: Implement the article pages**

`site/app/post/[slug]/page.js`:

```js
import { notFound } from "next/navigation";
import { getPost, loadPosts } from "../../../lib/content.js";
import { renderMarkdown } from "../../../lib/render.js";

export function generateStaticParams() {
  return loadPosts().map((p) => ({ slug: p.slug }));
}

export function generateMetadata({ params }) {
  const post = getPost(params.slug);
  return post ? { title: post.title, description: post.description } : {};
}

export default function PostPage({ params }) {
  const post = getPost(params.slug);
  if (!post) notFound();
  return (
    <article>
      <div className="text-xs text-slate-400 mb-2">
        {post.publishedAt.toISOString().slice(0, 10)} · {post.category}
      </div>
      <h1 className="text-3xl font-bold mb-6">{post.title}</h1>
      {post.titleAr && (
        <a href={`/ar/post/${post.slug}`} className="text-sm text-amber-400 mb-6 block">
          اقرأ بالعربية
        </a>
      )}
      <div className="space-y-4 leading-relaxed"
           dangerouslySetInnerHTML={{ __html: renderMarkdown(post.enMd) }} />
    </article>
  );
}
```

`site/app/ar/layout.js`:

```js
export default function ArLayout({ children }) {
  return <div dir="rtl" lang="ar" className="prose-ar">{children}</div>;
}
```

`site/app/ar/post/[slug]/page.js`:

```js
import { notFound } from "next/navigation";
import { getPost, loadPosts } from "../../../../lib/content.js";
import { renderMarkdown } from "../../../../lib/render.js";

export function generateStaticParams() {
  return loadPosts().filter((p) => p.arMd).map((p) => ({ slug: p.slug }));
}

export function generateMetadata({ params }) {
  const post = getPost(params.slug);
  return post && post.titleAr
    ? { title: post.titleAr, description: post.descriptionAr || post.description }
    : {};
}

export default function ArPostPage({ params }) {
  const post = getPost(params.slug);
  if (!post) notFound();
  return (
    <article>
      <div className="text-xs text-slate-400 mb-2">
        {post.publishedAt.toISOString().slice(0, 10)} · {post.category}
      </div>
      <h1 className="text-3xl font-bold mb-6">{post.titleAr || post.title}</h1>
      <a href={`/post/${post.slug}`} className="text-sm text-amber-400 mb-6 block">
        Read in English
      </a>
      {post.arMd ? (
        <div className="space-y-4 leading-relaxed"
             dangerouslySetInnerHTML={{ __html: renderMarkdown(post.arMd) }} />
      ) : (
        <p className="text-slate-400">النسخة العربية قريبًا.</p>
      )}
    </article>
  );
}
```

- [ ] **Step 5: Run tests, verify pages in dev**

```bash
cd site && npm test && npm run dev   # /post/saudi-port-expansion-2026 and /ar/post/...
```
Expected: render tests pass; both language pages display; AR page lays out RTL.

- [ ] **Step 6: Commit**

```bash
git add site/app/ site/lib/render.js site/tests/render.test.js
git commit -m "feat: bilingual article pages with rtl and link sanitization"
```

---

### Task 5: Category pages, 404, sitemap/robots, production build

**Files:**
- Create: `site/app/category/[slug]/page.js`, `site/app/not-found.js`, `site/app/sitemap.js`, `site/app/robots.js`
- Test: `npm run build` succeeds (integration check).

- [ ] **Step 1: Implement pages**

`site/app/category/[slug]/page.js`:

```js
import { notFound } from "next/navigation";
import PostCard from "../../../components/PostCard.jsx";
import { categories, loadPosts } from "../../../lib/content.js";

export function generateStaticParams() {
  return categories().map((c) => ({ slug: c.name }));
}

export function generateMetadata({ params }) {
  return { title: `Category: ${params.slug}` };
}

export default function CategoryPage({ params }) {
  const posts = loadPosts().filter((p) => p.category === params.slug);
  if (!posts.length) notFound();
  return (
    <>
      <h1 className="text-2xl font-bold mb-6 capitalize">{params.slug.replace(/-/g, " & ")}</h1>
      {posts.map((p) => <PostCard key={p.slug} post={p} />)}
    </>
  );
}
```

`site/app/not-found.js`:

```js
export default function NotFound() {
  return (
    <div className="text-center py-20">
      <h1 className="text-4xl font-bold mb-4">404</h1>
      <p className="text-slate-400">
        Page not found. <a href="/" className="text-amber-400">Back to latest</a>.
      </p>
    </div>
  );
}
```

`site/app/sitemap.js`:

```js
import { loadPosts } from "../lib/content.js";

export default function sitemap() {
  const base = "https://supplychainsparks.com";
  const posts = loadPosts();
  return [
    { url: base, changeFrequency: "daily", priority: 1 },
    ...posts.flatMap((p) => [
      { url: `${base}/post/${p.slug}`, lastModified: p.publishedAt, priority: 0.8 },
      ...(p.arMd ? [{ url: `${base}/ar/post/${p.slug}`, lastModified: p.publishedAt }] : []),
    ]),
  ];
}
```

`site/app/robots.js`:

```js
export default function robots() {
  return { rules: { userAgent: "*", allow: "/" },
           sitemap: "https://supplychainsparks.com/sitemap.xml" };
}
```

- [ ] **Step 2: Production build**

```bash
cd site && npm run build
```
Expected: build completes with static routes for `/`, both sample posts (EN + AR), categories, 404, sitemap.xml, robots.txt in `site/out/`.

- [ ] **Step 3: Commit**

```bash
git add site/app/
git commit -m "feat: category pages, 404, sitemap and robots"
```

---

### Task 6: Cloudflare Pages deployment

**Files:**
- Create: `docs/deploy-site.md`

- [ ] **Step 1: Write `docs/deploy-site.md`**

```markdown
# Deploying supplychainsparks.com (Cloudflare Pages)

1. Push the content repo (this repo or the dedicated content repo Plan 2 publishes to)
   to GitHub.
2. Cloudflare dashboard -> Workers & Pages -> Create -> Pages -> Connect to Git ->
   select the repo.
3. Build settings:
   - Framework preset: Next.js (Static HTML export)
   - Build command: `cd site && npm install && npm run build`
   - Build output directory: `site/out`
4. Add custom domain: supplychainsparks.com (Cloudflare DNS -> CNAME to the pages
   project; SSL is automatic).
5. Every push that changes `content/posts/**` or `site/**` triggers a rebuild;
   new articles are live ~1-2 minutes after Plan 2 publishes.

Notes:
- The site is fully static; it never depends on the local PC.
- Arabic pages live under /ar/ and render RTL.
```

- [ ] **Step 2: Deploy and verify**

Follow the doc: create the Pages project, connect the domain, confirm `https://supplychainsparks.com` serves the sample posts (or staging URL if the domain isn't purchased yet — the domain can be attached later without rebuild).

- [ ] **Step 3: Commit**

```bash
git add docs/deploy-site.md
git commit -m "docs: cloudflare pages deployment guide"
```

---

## Plan 3 completion checklist

After Task 6: the public site is live, bilingual, static, and auto-rebuilds on every content push from Plan 2. Spec §8 complete (home = latest + top stories this week; RTL Arabic; git-based publishing; site independent of the local PC). Sample posts may be removed once the first real story is published through the app — keep at least one post so category/nav pages always have content.

