import React, { useEffect, useState } from "react";
import QueueView from "./views/QueueView.jsx";
import StoryDetail from "./views/StoryDetail.jsx";
import ReviewView from "./views/ReviewView.jsx";
import PublishedView from "./views/PublishedView.jsx";
import SourcesView from "./views/SourcesView.jsx";
import Wizard from "./views/Wizard.jsx";
import { apiGet, apiPost } from "./api.js";

const Spark = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
    <path d="M8 1l1.8 4.5L14 7l-4.2 1.5L8 13l-1.8-4.5L2 7l4.2-1.5L8 1z" />
  </svg>
);

const ICONS = {
  queue: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor"
         strokeWidth="1.4" aria-hidden>
      <path d="M2.5 4h11M2.5 8h11M2.5 12h7" strokeLinecap="round" />
    </svg>
  ),
  review: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor"
         strokeWidth="1.4" aria-hidden>
      <path d="M2 13.5v-2l8-8 2 2-8 8h-2z" strokeLinejoin="round" />
      <path d="M9.5 4.5l2 2" />
    </svg>
  ),
  published: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor"
         strokeWidth="1.4" aria-hidden>
      <circle cx="8" cy="8" r="6" />
      <path d="M5.5 8.2l1.7 1.7 3.3-3.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  settings: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor"
         strokeWidth="1.4" aria-hidden>
      <circle cx="8" cy="8" r="2.2" />
      <path d="M8 1.8v2M8 12.2v2M1.8 8h2M12.2 8h2M3.6 3.6l1.4 1.4M11 11l1.4 1.4
               M12.4 3.6L11 5M5 11l-1.4 1.4" strokeLinecap="round" />
    </svg>
  ),
  sources: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor"
         strokeWidth="1.4" aria-hidden>
      <ellipse cx="8" cy="4" rx="5.5" ry="2.2" />
      <path d="M2.5 4v8c0 1.2 2.5 2.2 5.5 2.2s5.5-1 5.5-2.2V4" strokeLinecap="round" />
      <path d="M2.5 8c0 1.2 2.5 2.2 5.5 2.2s5.5-1 5.5-2.2" strokeLinecap="round" />
    </svg>
  ),
};

const TABS = ["queue", "review", "published", "sources", "settings"];

export default function App() {
  const [tab, setTab] = useState("queue");
  const [openStory, setOpenStory] = useState(null);
  const [status, setStatus] = useState(null);
  const [fetching, setFetching] = useState(false);
  const [flash, setFlash] = useState(null);       // {kind: "ok"|"error", text}
  const [queueKey, setQueueKey] = useState(0);    // bumped after each fetch cycle

  async function refreshStatus() {
    try { setStatus(await apiGet("/api/settings-status")); } catch { setStatus(null); }
  }
  useEffect(() => {
    refreshStatus();
    const t = setInterval(refreshStatus, 20000);
    return () => clearInterval(t);
  }, []);

  async function fetchNow() {
    setFetching(true);
    setFlash(null);
    try {
      const { job_id } = await apiPost("/api/fetch-now");
      const t = setInterval(async () => {
        try {
          const s = await apiGet(`/api/jobs/${job_id}`);
          if (s.state === "running") return;
          clearInterval(t);
          setFetching(false);
          if (s.state === "error" || s.error) {
            setFlash({ kind: "error",
                       text: `Fetch failed — ${s.error || "unknown error"}` });
            return;
          }
          const r = s.result || {};
          const errs = r.errors?.length ? ` · ${r.errors.length} source errors` : "";
          setFlash({ kind: "ok",
                     text: `${r.items_new ?? 0} new items · `
                         + `${r.stories_created ?? 0} new stories · `
                         + `${r.stories_judged ?? 0} judged${errs}` });
          setQueueKey((k) => k + 1);  // reload the queue with fresh stories
          refreshStatus();
        } catch (e) {
          clearInterval(t);
          setFetching(false);
          setFlash({ kind: "error", text: `Fetch failed — ${e}` });
        }
      }, 1500);
    } catch (e) {
      setFetching(false);
      setFlash({ kind: "error", text: `Fetch failed — ${e}` });
    }
  }

  const tier = status?.default_tier;

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <div className="brand-mark"><Spark /></div>
          <div>
            <div className="brand-name">Supply Chain Sparks</div>
            <div className="brand-sub">KSA · GCC INTELLIGENCE</div>
          </div>
        </div>

        {TABS.map((t) => (
          <button key={t} className={`nav-item ${tab === t ? "active" : ""}`}
                  onClick={() => { setTab(t); setOpenStory(null); }}>
            {ICONS[t]}
            <span>{t === "settings" ? "Setup" : t}</span>
          </button>
        ))}

        <div className="side-footer">
          <div className="status-row">
            <span className={`dot ${status ? "ok" : ""}`} />
            <span>{status ? "connected" : "offline"}</span>
          </div>
          <div className="status-row">
            <span className={`tier-chip ${tier === "local" ? "local" : ""}`}>
              {tier === "local" ? "LOCAL · OLLAMA" : "CLOUD · API"}
            </span>
          </div>
          <div className="status-row">
            <span>fetch every {status?.schedule_hours ?? "…"}h</span>
          </div>
        </div>
      </aside>

      <div className="main">
        <div className="page-head">
          <div>
            <h1 className="page-title">
              {tab === "queue" ? "Story queue" : tab === "review" ? "Review"
                : tab === "published" ? "Published"
                : tab === "sources" ? "Sources" : "Setup"}
            </h1>
            <p className="page-sub">
              {tab === "queue" ? "Ranked by editorial priority — select stories to publish"
                : tab === "review" ? "Edit, fact-check, approve"
                : tab === "published" ? "Publication archive with timestamps"
                : tab === "sources" ? "Where stories are fetched from"
                : "Engine, models and publishing"}
            </p>
          </div>
          <div className="page-actions">
            {tab === "queue" && (
              <button className="btn accent" onClick={fetchNow} disabled={fetching}>
                {fetching ? "Fetching…" : "Fetch now"}
              </button>
            )}
          </div>
        </div>

        {flash && <div className={`flash ${flash.kind}`}>{flash.text}</div>}

        <div className="content">
          {tab === "queue" && (openStory
            ? <StoryDetail storyId={openStory} onBack={() => setOpenStory(null)} />
            : <QueueView onSelect={setOpenStory} refreshKey={queueKey} />)}
          {tab === "review" && <ReviewView />}
          {tab === "published" && <PublishedView />}
          {tab === "sources" && <SourcesView />}
          {tab === "settings" && <Wizard onSaved={refreshStatus} />}
        </div>
      </div>
    </div>
  );
}
