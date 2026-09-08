import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

export default function StoryDetail({ storyId, onBack }) {
  const [data, setData] = useState(null);
  const [msg, setMsg] = useState("");

  async function refresh() {
    setData(await apiGet(`/api/stories/${storyId}`));
  }
  useEffect(() => { refresh(); }, [storyId]);

  if (!data) return <p>loading…</p>;
  const { story, sources, judge, generations } = data;

  async function generate(formats) {
    setMsg("generating…");
    const { job_id } = await apiPost(`/api/stories/${storyId}/generate`, { formats });
    poll(job_id);
  }
  async function poll(jobId) {
    const t = setInterval(async () => {
      const s = await apiGet(`/api/jobs/${jobId}`);
      if (s.state !== "running") {
        clearInterval(t);
        setMsg(s.state === "error" ? s.error : "done");
        refresh();
      }
    }, 1500);
  }

  return (
    <div className="detail">
      <button onClick={onBack}>← back</button>
      <h2>{story.title}</h2>
      <p>{story.band} · {story.priority} · {story.category} · {story.status}</p>
      {judge && (
        <div className="card">
          <p>💡 {judge.rationale_market_impact}</p>
          <p>{judge.gist}</p>
          <small>SC {judge.supply_chain_relevance}/10 · KSA {judge.saudi_gcc_relevance}/10 ·
            Impact {judge.market_impact}/10 · Novelty {judge.novelty}/10</small>
        </div>
      )}
      <div className="sources">
        <h4>Sources 🔒 <small>(local only — never published)</small></h4>
        <ul>{sources.map((s, i) => <li key={i}>{s.name} — {s.url}</li>)}</ul>
      </div>
      <div className="card-actions">
        <button onClick={() => generate(["article"])}>Generate articles (EN+AR)</button>
        <button onClick={() => generate(["linkedin"])}>Generate LinkedIn (EN+AR)</button>
      </div>
      {msg && <p>{msg}</p>}
      {generations.map((g) => (
        <div key={g.id} className="card">
          <b>{g.format} · {g.language}</b>
          <pre>{g.content}</pre>
        </div>
      ))}
    </div>
  );
}
