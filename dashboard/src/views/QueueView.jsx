import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

const BANDS = { high: "🔴", medium: "🟠", low: "🟢" };

export default function QueueView({ onSelect }) {
  const [stories, setStories] = useState([]);
  const [band, setBand] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const data = await apiGet(`/api/queue${band ? `?band=${band}` : ""}`);
      setStories(data.stories);
    } catch (e) { setError(String(e)); }
  }
  useEffect(() => { refresh(); }, [band]);

  async function select(id) {
    await apiPost(`/api/stories/${id}/select`);
    onSelect?.(id);
    refresh();
  }

  return (
    <div className="queue">
      <div className="queue-toolbar">
        {["", "high", "medium", "low"].map((b) => (
          <button key={b} className={band === b ? "active" : ""} onClick={() => setBand(b)}>
            {b || "all"}
          </button>
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      {stories.map((s) => (
        <div key={s.id} className={`card band-${s.band}`}>
          <div className="card-head">
            <span className="band">{BANDS[s.band]} {s.band}</span>
            <span className="priority">{s.priority?.toFixed(1)}</span>
            <span className="category">{s.category}</span>
            <span className="sources">{s.n_sources} sources</span>
          </div>
          <h3>{s.title}</h3>
          {s.judge && <p className="rationale">💡 {s.judge.rationale}</p>}
          {s.judge && <p className="gist">{s.judge.gist}</p>}
          <div className="card-actions">
            <button onClick={() => select(s.id)}>Select</button>
            <button onClick={() => onSelect?.(s.id)}>Open</button>
          </div>
        </div>
      ))}
      {!stories.length && !error && <p className="empty">Queue empty — run a fetch.</p>}
    </div>
  );
}
