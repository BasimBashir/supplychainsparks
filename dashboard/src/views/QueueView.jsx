import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

export default function QueueView({ onSelect }) {
  const [stories, setStories] = useState(null);
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
          <button key={b} className={`chip ${band === b ? "active" : ""}`}
                  onClick={() => setBand(b)}>
            {b === "" ? "all priorities" : b}
          </button>
        ))}
      </div>

      {error && <p className="empty">{error}</p>}

      {stories !== null && !stories.length && !error && (
        <div className="empty">
          <span className="big">⚡</span>
          The queue is empty. Run a fetch — stories appear here ranked by
          editorial priority.
        </div>
      )}

      {stories?.map((s) => (
        <div key={s.id} className={`story-card band-${s.band}`}>
          <div className="score-block">
            <div className="score-num">{s.priority?.toFixed(1) ?? "—"}</div>
            <div className="score-label">priority</div>
          </div>
          <div>
            <div className="story-head">
              <span className={`badge ${s.band}`}>{s.band}</span>
              <span className="badge ghost">{s.category || "uncategorized"}</span>
              <span className="badge ghost">{s.n_sources} source{s.n_sources === 1 ? "" : "s"}</span>
            </div>
            <h3 className="story-title">{s.title}</h3>
            {s.judge && (
              <p className="rationale">
                💡 <b>Impact {s.judge.scores.impact}/10</b> — {s.judge.rationale}
              </p>
            )}
            {s.judge && <p className="gist">{s.judge.gist}</p>}
            <div className="card-actions">
              <button className="btn accent small" onClick={() => select(s.id)}>Select</button>
              <button className="btn subtle small" onClick={() => onSelect?.(s.id)}>Open</button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
