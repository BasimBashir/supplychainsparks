import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

export default function ReviewDetail({ storyId, onBack }) {
  const [data, setData] = useState(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  async function refresh() {
    setData(await apiGet(`/api/stories/${storyId}`));
  }
  useEffect(() => { refresh(); }, [storyId]);

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

  if (!data) return <p className="empty">loading…</p>;
  const generations = data.generations || [];
  const openFlags = data.open_flags || [];
  const en = generations.find((g) => g.format === "article" && g.language === "en");
  const ar = generations.find((g) => g.format === "article" && g.language === "ar");
  const li = generations.filter((g) => g.format === "linkedin");
  const blocked = openFlags.length > 0 || !generations.length;

  async function save(genId, content) {
    setSaving(true);
    await apiPost(`/api/generations/${genId}`, { content });
    setSaving(false);
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
    try {
      await apiPost(`/api/flags/${id}/resolve`, { resolution: "resolved_confirm" });
      refresh();
      setMsg("Flag resolved ✓");
    } catch (e) {
      setMsg(`Failed to resolve flag: ${String(e)}`);
    }
  }
  async function approve() {
    await apiPost(`/api/stories/${storyId}/approve`);
    refresh();
  }
  async function publish(destinations) {
    await apiPost(`/api/stories/${storyId}/publish`, { destinations });
    refresh();
  }

  async function remove() {
    if (!window.confirm(`Delete “${data.story.title}”?\n\nThis removes the story and its ` +
                        `clipped articles from this PC. It cannot be undone.`))
      return;
    try {
      await apiPost(`/api/stories/${storyId}/delete`);
      onBack();
    } catch (e) { setMsg(String(e)); }
  }

  return (
    <div className="editor card">
      <div className="back-row">
        <button className="btn subtle" onClick={onBack}>← Back to review</button>
      </div>
      <div className="detail-head">
        <h2>{data.story.title}</h2>
        <span className="meta-line">
          status: {data.story.status} · priority: {data.story.priority?.toFixed(1) ?? "—"} · {data.story.category || "uncategorized"}
        </span>
      </div>

      <div className="card-actions">
        <button className="btn accent small" onClick={() => generate(["article"])}>
          Generate articles (EN + AR)
        </button>
        <button className="btn small" onClick={() => generate(["linkedin"])}>
          Generate LinkedIn (EN + AR)
        </button>
        <button className="btn subtle small" onClick={() => generate(["article", "linkedin"])}>
          Generate all
        </button>
        <button className="btn danger small" onClick={remove}>Delete story</button>
      </div>
      {msg && <p className="gist" style={{ marginTop: 10 }}>{msg}</p>}

      <div className="review-grid">
        <div>
          <h3>English</h3>
          <EditorArea gen={en} onSave={save} onFactCheck={factCheck} />
          {en && <div className="card-actions" style={{ marginTop: 8 }}>
            <button className="btn small" onClick={() => generate(["article"])}>Regenerate EN+AR articles</button>
          </div>}
        </div>
        <div dir="rtl">
          <h3>العربية</h3>
          <EditorArea gen={ar} onSave={save} onFactCheck={factCheck} />
        </div>
      </div>

      {li.map((g) => (
        <div key={g.id} className="card" style={{ background: "#171b22" }}>
          <b>LinkedIn · {g.language === "ar" ? "العربية" : "English"}</b>
          <pre className="gen-preview">{g.content}</pre>
          <div className="card-actions">
            <CopyButton text={g.content} />
            <button className="btn subtle small"
                    onClick={() => publish(["linkedin"])}>Mark copied</button>
            <button className="btn small" onClick={() => generate(["linkedin"])}>Regenerate</button>
          </div>
        </div>
      ))}

      <h4 style={{ margin: "14px 0 6px", fontSize: 12, textTransform: "uppercase",
                    letterSpacing: "0.5px", color: "var(--text-low)" }}>
        Fact-check flags
      </h4>
      {openFlags.length === 0
        ? <p className="ok-note">no open flags ✓</p>
        : openFlags.map((f) => (
          <div key={f.id} className="flag">
            <span>⚠ <b>{f.claim}</b></span>
            <span className="verdict">{f.verdict}</span>
            <button className="btn small" onClick={() => resolve(f.id)}>resolve</button>
          </div>
        ))}

      <div className="card-actions" style={{ marginTop: 14 }}>
        <button className="btn accent" disabled={blocked} onClick={approve}>
          Approve
        </button>
        <button className="btn" disabled={data.story.status !== "approved"}
                onClick={() => publish(["site"])}>
          Publish to website
        </button>
      </div>
    </div>
  );
}

function EditorArea({ gen, onSave, onFactCheck }) {
  const [text, setText] = useState(gen?.content || "");
  useEffect(() => { setText(gen?.content || ""); }, [gen?.id]);
  if (!gen) return <p className="gist">not generated yet</p>;
  return <div>
    <textarea value={text} onChange={(e) => setText(e.target.value)}
              dir={gen.language === "ar" ? "rtl" : "ltr"} />
    <div className="card-actions">
      <button className="btn small" onClick={() => onSave(gen.id, text)}>Save</button>
      <button className="btn subtle small" onClick={() => onFactCheck(gen.id)}>
        Fact-check
      </button>
      <span className="editor-meta">{text.length} chars</span>
    </div>
  </div>;
}

function CopyButton({ text }) {
  const [done, setDone] = useState(false);
  return <button className="btn small" onClick={async () => {
    await navigator.clipboard.writeText(text);
    setDone(true);
    setTimeout(() => setDone(false), 1500);
  }}>{done ? "copied ✓" : "Copy"}</button>;
}