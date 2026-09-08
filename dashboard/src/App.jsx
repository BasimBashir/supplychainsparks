import React, { useEffect, useState } from "react";
import QueueView from "./views/QueueView.jsx";
import StoryDetail from "./views/StoryDetail.jsx";
import ReviewView from "./views/ReviewView.jsx";
import PublishedView from "./views/PublishedView.jsx";
import Wizard from "./views/Wizard.jsx";
import { apiGet } from "./api.js";

const TABS = ["queue", "review", "published", "settings"];

export default function App() {
  const [tab, setTab] = useState("queue");
  const [openStory, setOpenStory] = useState(null);
  const [status, setStatus] = useState({});

  useEffect(() => {
    const t = setInterval(async () => {
      try { setStatus(await apiGet("/api/health")); } catch { /* server away */ }
    }, 15000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="app">
      <header>
        <h1>⚡ Supply Chain Sparks</h1>
        <nav>{TABS.map((t) => (
          <button key={t} className={tab === t ? "active" : ""}
                  onClick={() => { setTab(t); setOpenStory(null); }}>{t}</button>
        ))}</nav>
      </header>
      <main>
        {tab === "queue" && (openStory
          ? <StoryDetail storyId={openStory} onBack={() => setOpenStory(null)} />
          : <QueueView onSelect={setOpenStory} />)}
        {tab === "review" && <ReviewView onOpen={setOpenStory} />}
        {tab === "published" && <PublishedView />}
        {tab === "settings" && <Wizard />}
      </main>
      <footer>status: {status.status || "…"} </footer>
    </div>
  );
}
