import React, { useEffect, useState } from "react";
import { apiGet } from "../api.js";

export default function ReviewView({ onSelect }) {
  const [data, setData] = useState(null);

  async function refresh() {
    setData(await apiGet("/api/review"));
  }
  useEffect(() => { refresh(); }, []);
  if (!data) return <p className="empty">loading…</p>;

  const stories = data.stories;
  return (
    <div>
      {!stories.length && (
        <div className="empty">
          <span className="big">✎</span>
          Nothing in review. Select stories from the queue, generate content,
          then polish them here.
        </div>
      )}
      {stories.map((s) => (
        <div key={s.id} className={`story-card band-${s.band} review`}
             onClick={() => onSelect?.(s.id)}
             style={{ cursor: "pointer" }}>
          <div className="score-block">
            <div className="score-num">{s.priority?.toFixed(1) ?? "—"}</div>
            <div className="score-label">priority</div>
          </div>
          <div>
            <div className="story-head">
              <span className="badge ghost">{s.status}</span>
              <span className="badge ghost">{s.category || "uncategorized"}</span>
            </div>
            <h3 className="story-title">{s.title}</h3>
            <p className="gist">{s.generation_count} generation{s.generation_count === 1 ? "" : "s"}</p>
          </div>
        </div>
      ))}
    </div>
  );
}