import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

export default function StoryDetail({ storyId, onBack }) {
  const [data, setData] = useState(null);
  const [msg, setMsg] = useState("");

  async function refresh() {
    setData(await apiGet(`/api/stories/${storyId}`));
  }
  useEffect(() => { refresh(); }, [storyId]);

  if (!data) return <p className="empty">loading…</p>;
  const { story, sources, judge, generations } = data;

  async function generate(formats) {
    setMsg("generating…");
    try {
      const { job_id } = await apiPost(`/api/stories/${storyId}/generate`, { formats });
      poll(job_id);
    } catch (e) { setMsg(String(e)); }
  }
  async function poll(jobId) {
    const t = setInterval(async () => {
      const s = await apiGet(`/api/jobs/${jobId}`);
      if (s.state !== "running") {
        clearInterval(t);
        setMsg(s.state === "error" ? `generation failed: ${s.error}` : "done ✓");
        refresh();
      }
    }, 1500);
  }

  async function remove() {
    if (!window.confirm(`Delete “${story.title}”?\n\nThis removes the story and its ` +
                        `clipped articles from this PC. It cannot be undone.`))
      return;
    try {
      await apiPost(`/api/stories/${storyId}/delete`);
      onBack();
    } catch (e) { setMsg(String(e)); }
  }

  return (
    <div className="detail">
      <div className="back-row">
        <button className="btn subtle small" onClick={onBack}>← Back to queue</button>
      </div>

      <div className="card">
        <div className="detail-head">
          <h2>{story.title}</h2>
          <span className={`badge ${story.band}`}>{story.band}</span>
          <span className="badge ghost">{story.category || "uncategorized"}</span>
          <span className="badge ghost">{story.status}</span>
        </div>
        <p className="meta-line">
          priority {story.priority?.toFixed(1)} · judge: {story.judge_status}
        </p>

        {judge && (
          <div className="judge-box">
            <p className="rationale">💡 <b>Impact {judge.market_impact}/10</b> — {judge.rationale_market_impact}</p>
            <p className="gist">{judge.gist}</p>
            <div className="judge-scores">
              <span>supply chain <b>{judge.supply_chain_relevance}/10</b></span>
              <span>ksa/gcc <b>{judge.saudi_gcc_relevance}/10</b></span>
              <span>impact <b>{judge.market_impact}/10</b></span>
              <span>novelty <b>{judge.novelty}/10</b></span>
            </div>
          </div>
        )}

        <div className="sources-box">
          <h4>Sources 🔒 local record only — never published</h4>
          <ul>{sources.map((s, i) => (
            <li key={i}><span className="src-name">{s.name}</span> — {s.url}</li>
          ))}</ul>
        </div>

        <div className="card-actions">
          <button className="btn accent small" onClick={() => generate(["article"])}>
            Generate articles (EN + AR)
          </button>
          <button className="btn small" onClick={() => generate(["linkedin"])}>
            Generate LinkedIn (EN + AR)
          </button>
          {story.status !== "published" && (
            <button className="btn danger small" onClick={remove}>Delete story</button>
          )}
        </div>
        {msg && <p className="gist" style={{ marginTop: 10 }}>{msg}</p>}
      </div>

      {generations.map((g) => (
        <div key={g.id} className="card">
          <b>{g.format === "article" ? "Article" : "LinkedIn post"} · {g.language === "ar" ? "العربية" : "English"}</b>
          <pre className="gen-preview">{g.content}</pre>
        </div>
      ))}
    </div>
  );
}
