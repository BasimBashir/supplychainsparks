import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

export default function QueueView({ onSelect, refreshKey = 0 }) {
  const [stories, setStories] = useState(null);
  const [band, setBand] = useState("");
  const [unscoredCount, setUnscoredCount] = useState(0);
  const [error, setError] = useState("");
  const [selectedIds, setSelectedIds] = useState(new Set());

  async function refresh() {
    try {
      const data = await apiGet(`/api/queue${band ? `?band=${band}` : ""}`);
      setStories(data.stories);
      setUnscoredCount(data.unscored_count ?? 0);
    } catch (e) { setError(String(e)); }
  }
  useEffect(() => { refresh(); }, [band, refreshKey]);
  useEffect(() => { setSelectedIds(new Set()); }, [band]);

  function toggleSelect(id) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll(checked) {
    if (checked && stories) {
      setSelectedIds(new Set(stories.map(s => s.id)));
    } else {
      setSelectedIds(new Set());
    }
  }

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

  async function bulkRemove() {
    if (!selectedIds.size) return;
    const titles = stories?.filter(s => selectedIds.has(s.id)).map(s => s.title).join("; ") || "";
    if (!window.confirm(`Delete ${selectedIds.size} story(s)?\n\n${titles}\n\n` +
                        `This cannot be undone.`))
      return;
    try {
      const r = await apiPost("/api/stories/bulk-delete", { ids: Array.from(selectedIds) });
      setError(r.skipped_published
        ? `Deleted ${r.count} story(s), skipped ${r.skipped_published} published`
        : `Deleted ${r.count} story(s)`);
      setSelectedIds(new Set());
      refresh();
    } catch (e) { setError(String(e)); }
  }

  const allSelected = stories && stories.length > 0 && selectedIds.size === stories.length;
  const hasDeletable = stories?.some(s => selectedIds.has(s.id) && s.status !== "published") ?? false;

  return (
    <div className="queue">
      <div className="queue-toolbar">
        {["", "high", "medium", "low", "unscored"].map((b) => (
          <button key={b} className={`chip ${band === b ? "active" : ""}`}
                  onClick={() => setBand(b)}>
            {b === "" ? "all priorities" : b}
          </button>
        ))}
        {selectedIds.size > 0 && (
          <div className="bulk-actions-inline">
            <span className="bulk-count">{selectedIds.size} selected</span>
            {hasDeletable && (
              <button className="btn danger small" onClick={bulkRemove}>
                Delete selected
              </button>
            )}
            <button className="btn subtle small" onClick={() => setSelectedIds(new Set())}>
              Clear selection
            </button>
          </div>
        )}
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

      {stories && stories.length > 0 && (
        <>
          <div className="bulk-select-header">
            <label>
              <input type="checkbox" checked={allSelected} onChange={e => selectAll(e.target.checked)} />
              <span>Select all ({stories.length})</span>
            </label>
          </div>
          {stories.map((s) => (
            <div key={s.id} className={`story-card band-${s.band} ${selectedIds.has(s.id) ? "selected" : ""}`}>
              <input type="checkbox" className="row-select"
                     checked={selectedIds.has(s.id)}
                     onChange={() => toggleSelect(s.id)} />
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
        </>
      )}
    </div>
  );
}
