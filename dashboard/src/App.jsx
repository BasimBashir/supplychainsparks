import React, { useEffect, useState } from "react";
import QueueView from "./views/QueueView.jsx";
import StoryDetail from "./views/StoryDetail.jsx";
import ReviewView from "./views/ReviewView.jsx";
import PublishedView from "./views/PublishedView.jsx";
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
};

const TABS = ["queue", "review", "published", "settings"];

export default function App() {
  const [tab, setTab] = useState("queue");
  const [openStory, setOpenStory] = useState(null);
  const [status, setStatus] = useState(null);
  const [fetching, setFetching] = useState(false);

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
    try {
      const { job_id } = await apiPost("/api/fetch-now");
      const t = setInterval(async () => {
        const s = await apiGet(`/api/jobs/${job_id}`);
        if (s.state !== "running") { clearInterval(t); setFetching(false); refreshStatus(); }
      }, 1500);
    } catch { setFetching(false); }
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
                : tab === "published" ? "Published" : "Setup"}
            </h1>
            <p className="page-sub">
              {tab === "queue" ? "Ranked by editorial priority — select stories to publish"
                : tab === "review" ? "Edit, fact-check, approve"
                : tab === "published" ? "Publication archive with timestamps"
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

        <div className="content">
          {tab === "queue" && (openStory
            ? <StoryDetail storyId={openStory} onBack={() => setOpenStory(null)} />
            : <QueueView onSelect={setOpenStory} />)}
          {tab === "review" && <ReviewView />}
          {tab === "published" && <PublishedView />}
          {tab === "settings" && <Wizard onSaved={refreshStatus} />}
        </div>
      </div>
    </div>
  );
}
