import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

export default function ReviewView({ onOpen }) {
  const [data, setData] = useState(null);
  const [editingId, setEditingId] = useState(null);

  async function refresh() {
    setData(await apiGet("/api/queue"));
  }
  useEffect(() => { refresh(); }, []);
  if (!data) return <p>loading…</p>;

  const selected = data.stories.filter((s) =>
    ["selected", "generating", "review", "approved"].includes(s.status));
  return (
    <div>
      <h2>Review</h2>
      {!selected.length &&
        <p className="empty">Nothing in review — select stories from the queue.</p>}
      {selected.map((s) => (
        <div key={s.id} className="card" onClick={() => setEditingId(s.id)}>
          <b>{s.title}</b> <span className="category">{s.status}</span>
        </div>
      ))}
      {editingId && <StoryEditor key={editingId} storyId={editingId} />}
    </div>
  );
}

function StoryEditor({ storyId }) {
  const [data, setData] = useState(null);

  async function refresh() {
    setData(await apiGet(`/api/stories/${storyId}`));
  }
  useEffect(() => { refresh(); }, [storyId]);

  if (!data) return <p>loading…</p>;
  const generations = data.generations || [];
  const openFlags = data.open_flags || [];
  const en = generations.find((g) => g.format === "article" && g.language === "en");
  const ar = generations.find((g) => g.format === "article" && g.language === "ar");
  const li = generations.filter((g) => g.format === "linkedin");
  const blocked = openFlags.length > 0 || !generations.length;

  async function save(genId, content) {
    await apiPost(`/api/generations/${genId}`, { content });
    refresh();
  }
  async function factCheck(genId) {
    const { job_id } = await apiPost(`/api/generations/${genId}/fact-check`);
    const t = setInterval(async () => {
      const s = await apiGet(`/api/jobs/${job_id}`);
      if (s.state !== "running") { clearInterval(t); refresh(); }
    }, 1500);
  }
  async function resolve(id) {
    await apiPost(`/api/flags/${id}/resolve`, { resolution: "resolved_confirm" });
    refresh();
  }
  async function approve() {
    await apiPost(`/api/stories/${storyId}/approve`);
    refresh();
  }
  async function publish(destinations) {
    await apiPost(`/api/stories/${storyId}/publish`, { destinations });
    refresh();
  }

  return (
    <div className="editor">
      <div className="review-grid">
        <div>
          <h3>English</h3>
          <EditorArea gen={en} onSave={save} onFactCheck={factCheck} />
        </div>
        <div dir="rtl">
          <h3>العربية</h3>
          <EditorArea gen={ar} onSave={save} onFactCheck={factCheck} />
        </div>
      </div>
      {li.map((g) => (
        <div key={g.id} className="card">
          <b>LinkedIn · {g.language}</b>
          <pre>{g.content}</pre>
          <CopyButton text={g.content} />
          <button onClick={() => publish(["linkedin"])}>Mark copied</button>
        </div>
      ))}
      <h4>Fact flags</h4>
      {openFlags.length === 0 && <p className="ok">no open flags ✓</p>}
      {openFlags.map((f) => (
        <div key={f.id} className="flag">
          ⚠ <b>{f.claim}</b> — {f.verdict}{" "}
          <button onClick={() => resolve(f.id)}>resolve</button>
        </div>
      ))}
      <div className="card-actions">
        <button disabled={blocked} onClick={approve}>Approve</button>
        <button disabled={data.story.status !== "approved"} onClick={() => publish(["site"])}>
          Publish to site
        </button>
      </div>
    </div>
  );
}

function EditorArea({ gen, onSave, onFactCheck }) {
  const [text, setText] = useState(gen?.content || "");
  useEffect(() => { setText(gen?.content || ""); }, [gen?.id]);
  if (!gen) return <p>not generated yet</p>;
  return <div>
    <textarea value={text} onChange={(e) => setText(e.target.value)}
              dir={gen.language === "ar" ? "rtl" : "ltr"} />
    <div className="card-actions">
      <button onClick={() => onSave(gen.id, text)}>Save</button>
      <button onClick={() => onFactCheck(gen.id)}>Fact-check</button>
      <span className="category">{text.length} chars</span>
    </div>
  </div>;
}

function CopyButton({ text }) {
  const [done, setDone] = useState(false);
  return <button onClick={async () => {
    await navigator.clipboard.writeText(text);
    setDone(true);
    setTimeout(() => setDone(false), 1500);
  }}>{done ? "copied ✓" : "Copy"}</button>;
}
