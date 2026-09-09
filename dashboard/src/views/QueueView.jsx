import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

export default function QueueView({ onSelect, refreshKey = 0 }) {
  const [stories, setStories] = useState(null);
  const [band, setBand] = useState("");
  const [unscoredCount, setUnscoredCount] = useState(0);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const data = await apiGet(`/api/queue${band ? `?band=${band}` : ""}`);
      setStories(data.stories);
      setUnscoredCount(data.unscored_count ?? 0);
    } catch (e) { setError(String(e)); }
  }
  useEffect(() => { refresh(); }, [band, refreshKey]);

  async function select(id) {
    await apiPost(`/api/stories/${id}/select`);
    onSelect?.(id);
    refresh();
  }

  async function remove(s) {
    if (!window.confirm(`Delete “${s.title}”?\n\nThis removes the story and its ` +
                        `clipped articles from this PC. It cannot be undone.`))
      return;
    try {
      await apiPost(`/api/stories/${s.id}/delete`);
      refresh();
    } catch (e) { setError(String(e)); }
  }

  return (
    <div className="queue">
      <div className="queue-toolbar">
        {["", "high", "medium", "low", "unscored"].map((b) => (
          <button key={b} className={`chip ${band === b ? "active" : ""}`}
                  onClick={() => setBand(b)}>
            {b === "" ? "all priorities" : b}
          </button>
        ))}
      </div>

      {error && <p className="empty">{error}</p>}

      {band !== "unscored" && unscoredCount > 0 && (
        <div className="unscored-note">
          ⚖ {unscoredCount} stories waiting to be scored — no judge is available
          (missing API key or Ollama model). They rank automatically once judging
          works.{" "}
          <button className="link" onClick={() => setBand("unscored")}>Show them</button>
        </div>
      )}

      {stories !== null && !stories.length && !error && (
        <div className="empty">
          <span className="big">⚡</span>
          {band === "unscored"
            ? "Nothing waiting — every story is scored."
            : <>The queue is empty. Run a fetch — stories appear here ranked by
               editorial priority.</>}
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
              {s.status !== "published" && (
                <button className="btn danger small" onClick={() => remove(s)}>Delete</button>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
